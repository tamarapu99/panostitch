"""Pose-guided 360 equirectangular stitch for the guided-capture package.

Every shot is placed on the sphere from its device quaternion (conceptdash.capture/2),
optionally refined by per-shot rotation corrections (see refine_poses.py), then
blended with distance-to-edge feathering.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

ROOT = "captured_input"
ROOM = 0
SCALE = 0.5            # work on half-res source images
FOCAL_PX_FULL = 3065   # ~26 mm-equivalent main camera on a 3060x4080 sensor image
OUT_W = 4096
CENTER_AZ = None       # azimuth drawn at the panorama centre (default: room headingYaw)
CORR_FILE = "pose_corrections.json"


def quat_to_R(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def load_shots():
    home = json.load(open(os.path.join(ROOT, "home.json")))
    room = home["rooms"][ROOM]
    shots = []
    for s in room["shots"]:
        img = cv2.imread(os.path.join(ROOT, s["file"]))
        img = cv2.resize(img, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)
        shots.append({"name": s["target"], "img": img, "R": quat_to_R(s["pose"]["quaternion"]),
                      "quality": s.get("quality", {})})
    add_quality_weights(shots)
    return shots, room.get("headingYaw", 0.0)


def add_quality_weights(shots):
    """Seam-ownership multiplier: blurrier / more drifted shots lose ties to sharper, steadier ones."""
    sharp = np.array([s["quality"].get("sharpness", 0) for s in shots], np.float64)
    med = np.median(sharp[sharp > 0]) if (sharp > 0).any() else 1.0
    for s, sh in zip(shots, sharp):
        drift = s["quality"].get("driftDeg", 0.0)
        s["qw"] = float(np.clip(sh / med if sh > 0 else 1.0, 0.6, 1.4) / (1 + drift / 5.0))


def apply_corrections(shots):
    if os.path.exists(CORR_FILE):
        corr = json.load(open(CORR_FILE))
        for s in shots:
            if s["name"] in corr:
                rv = np.array(corr[s["name"]], dtype=np.float64)
                s["R"] = cv2.Rodrigues(rv)[0] @ s["R"]
    return shots


def focal():
    scale = 1.0
    if os.path.exists(CORR_FILE):
        scale = json.load(open(CORR_FILE)).get("focal_scale", 1.0)
    return FOCAL_PX_FULL * SCALE * scale


def sphere_dirs(W, H, center_az):
    u = (np.arange(W) + 0.5) / W
    v = (np.arange(H) + 0.5) / H
    az = np.radians(center_az) + (u - 0.5) * 2 * np.pi
    el = (0.5 - v) * np.pi
    az, el = np.meshgrid(az, el)
    return np.stack([np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.sin(el)], -1)


def project(shot, dirs, f):
    """Return (map_x, map_y, weight) sampling `shot` for each world direction."""
    h, w = shot["img"].shape[:2]
    cam = dirs @ shot["R"]            # == R^T d for each row
    k = -cam[..., 2]
    ok = k > 1e-6
    ks = np.where(ok, k, 1.0)
    x = f * cam[..., 0] / ks + w / 2
    y = -f * cam[..., 1] / ks + h / 2
    inside = ok & (x >= 0) & (x < w - 1) & (y >= 0) & (y < h - 1)
    dx = np.minimum(x, w - 1 - x) / (w / 2)
    dy = np.minimum(y, h - 1 - y) / (h / 2)
    wgt = np.where(inside, np.clip(np.minimum(dx, dy), 0, 1), 0.0)
    return x.astype(np.float32), y.astype(np.float32), wgt.astype(np.float32)


def exposure_gains(shots, dirs, f, step=4):
    """Per-channel (B, G, R) gain per shot so overlapping shots agree in brightness and colour."""
    sm = dirs[::step, ::step]
    samples = []
    for s in shots:
        mx, my, wg = project(s, sm, f)
        v = cv2.remap(s["img"], mx, my, cv2.INTER_LINEAR).astype(np.float32)
        gray = v.mean(-1)
        samples.append((v, (wg > 0.15) & (gray > 25) & (gray < 225)))
    n = len(shots)
    rows = []
    rhs = [[], [], []]
    for i in range(n):
        for j in range(i + 1, n):
            m = samples[i][1] & samples[j][1]
            if m.sum() < 500:
                continue
            r = np.zeros(n)
            r[i], r[j] = 1, -1
            rows.append(r)
            for c in range(3):
                rhs[c].append(np.log(samples[j][0][..., c][m].mean() + 1) - np.log(samples[i][0][..., c][m].mean() + 1))
    if not rows:
        return np.ones((n, 3))
    A = np.vstack(rows + [np.ones((1, n)) * 2.0])
    gains = np.empty((n, 3))
    for c in range(3):
        lg = np.linalg.lstsq(A, np.array(rhs[c] + [0.0]), rcond=None)[0]
        gains[:, c] = np.exp(np.clip(lg, -0.25, 0.25))
    return gains


def pyr_down_gauss(img, levels):
    out = [img]
    for _ in range(levels):
        out.append(cv2.pyrDown(out[-1]))
    return out


def render(shots, W, f, center_az, levels=6, gains=True):
    """Voronoi-style seams (each pixel owned by the shot it is most central in) blended with a multiband pyramid."""
    H = W // 2
    dirs = sphere_dirs(W, H, center_az)
    g = exposure_gains(shots, dirs, f) if gains else np.ones((len(shots), 3))
    print("exposure gains (B,G,R) min/max:", np.round(g.min(0), 2), np.round(g.max(0), 2))
    best = np.zeros((H, W), np.float32)
    owner = np.zeros((H, W), np.int16)
    count = np.zeros((H, W), np.uint8)
    for i, s in enumerate(shots):
        wg = project(s, dirs, f)[2]
        count += wg > 0
        wq = wg * s["qw"]
        upd = wq > best
        best[upd] = wq[upd]
        owner[upd] = i
    covered = best > 0
    out_pyr = None
    wsum_pyr = None
    for i, s in enumerate(shots):
        mx, my, wg = project(s, dirs, f)
        mask = ((owner == i) & covered).astype(np.float32)
        if not mask.any():
            continue
        # widen the ownership slightly toward neighbours so seams blend over real overlap
        mask = cv2.GaussianBlur(mask, (0, 0), 6)
        mask *= (wg > 0)
        warped = cv2.remap(s["img"], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).astype(np.float32) * g[i]
        gp = pyr_down_gauss(warped, levels)
        lp = [gp[k] - cv2.pyrUp(gp[k + 1], dstsize=(gp[k].shape[1], gp[k].shape[0])) for k in range(levels)] + [gp[levels]]
        mp = pyr_down_gauss(mask, levels)
        if out_pyr is None:
            out_pyr = [np.zeros_like(l) for l in lp]
            wsum_pyr = [np.zeros(l.shape[:2], np.float32) for l in lp]
        for k in range(levels + 1):
            out_pyr[k] += lp[k] * mp[k][..., None]
            wsum_pyr[k] += mp[k]
    bands = [out_pyr[k] / np.maximum(wsum_pyr[k], 1e-6)[..., None] for k in range(levels + 1)]
    img = bands[levels]
    for k in range(levels - 1, -1, -1):
        img = cv2.pyrUp(img, dstsize=(bands[k].shape[1], bands[k].shape[0])) + bands[k]
    img = np.clip(img, 0, 255).astype(np.uint8)
    return fill_gaps(img, covered), covered, count


def fill_gaps(img, covered):
    """Inpaint uncovered pixels (zenith/nadir holes) on a small copy, then paste only into the holes."""
    if covered.all():
        return img
    H, W = covered.shape
    hole = (~covered).astype(np.uint8)
    hole = cv2.dilate(hole, np.ones((5, 5), np.uint8))
    sw, sh = W // 8, H // 8
    small = cv2.resize(img, (sw, sh), interpolation=cv2.INTER_AREA)
    small_mask = (cv2.resize(hole, (sw, sh), interpolation=cv2.INTER_AREA) > 0).astype(np.uint8)
    filled = cv2.inpaint(small, small_mask, 5, cv2.INPAINT_TELEA)
    up = cv2.resize(filled, (W, H), interpolation=cv2.INTER_CUBIC)
    out = img.copy()
    out[hole > 0] = up[hole > 0]
    return out


def report(covered, count, shots):
    H = covered.shape[0]
    el = (0.5 - (np.arange(H) + 0.5) / H) * 180
    print("coverage: %.1f%% (>=2 shots overlap: %.1f%%)" % (100 * covered.mean(), 100 * (count >= 2).mean()))
    for name, lo, hi in [("zenith  >60", 60, 90), ("up 20..60", 20, 60), ("level +-20", -20, 20),
                         ("down -60..-20", -60, -20), ("nadir  <-60", -90, -60)]:
        band = (el >= lo) & (el < hi) if hi < 90 else (el >= lo)
        print("  %-14s covered %.1f%%  overlap>=2 %.1f%%" % (name, 100 * covered[band].mean(), 100 * (count[band] >= 2).mean()))
    if os.path.exists(CORR_FILE):
        corr = json.load(open(CORR_FILE))
        deg = [np.degrees(np.linalg.norm(corr[s["name"]])) for s in shots if s["name"] in corr]
        if deg:
            print("pose corrections: mean %.1f deg, max %.1f deg (focal_scale %.3f)" % (np.mean(deg), np.max(deg), corr.get("focal_scale", 1.0)))
    print("shot quality weights:", np.round([s["qw"] for s in shots], 2))


def main(out_path):
    shots, heading = load_shots()
    shots = apply_corrections(shots)
    center = heading if CENTER_AZ is None else CENTER_AZ
    pano, covered, count = render(shots, OUT_W, focal(), center)
    cv2.imwrite(out_path, pano, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print("saved", out_path, pano.shape)
    report(covered, count, shots)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="output_images/pose_panorama.jpg")
    ap.add_argument("--width", type=int, default=OUT_W, help="equirect width (height = width/2)")
    ap.add_argument("--scale", type=float, default=SCALE, help="source image scale, 1.0 = full-res")
    a = ap.parse_args()
    OUT_W, SCALE = a.width, a.scale
    os.makedirs("output_images", exist_ok=True)
    main(a.out)
