"""Improved render of the captured room, built on pose_stitch.py (imported, not edited).

Removes the photographer's feet: the feet are only in the nadir shot (in the down-ring shots the
photographer stands behind the phone), so the nadir shot is made to lose every seam it shares
with another shot and only fills the small cap below the down ring.

Whatever is left of the feet sits where only the nadir shot sees the floor. Those pixels are found
by colour (skin and jeans stand out from the grey floor) and replaced with floor texture copied
from beside them on the same rows, blended in with Poisson cloning.

Ceiling: the zenith shot gets more seam weight, because the up-ring shots see the fan rod at a
steep angle and smear it across the ceiling (x3 tested best; x6 and up smear the beams).

Usage: python improve_pano.py [out.jpg] [--width 4096] [--scale 0.5] [--nadir-weight 0.0001] [--zenith-weight 3] [--keep-feet]
"""
import argparse
import os

import cv2
import numpy as np

import pose_stitch as ps


def nadir_only(shots, W, center, f):
    """Pixels no shot except the nadir shot can see."""
    dirs = ps.sphere_dirs(W, W // 2, center)
    others = np.zeros((W // 2, W), bool)
    for s in shots:
        if s["name"] != "nadir":
            others |= ps.project(s, dirs, f)[2] > 0
    return ~others


def feet_mask(pano, only_nadir, min_area=1000):
    """Coloured blobs (skin, jeans) inside the nadir-only area, grown to cover their shadows."""
    hsv = cv2.cvtColor(pano, cv2.COLOR_BGR2HSV)
    area = cv2.dilate(only_nadir.astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
    floor_sat = np.median(hsv[..., 1][area])
    cand = (area & (hsv[..., 1] > floor_sat + 16)).astype(np.uint8)
    cand = cv2.morphologyEx(cand, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(cand)
    keep = np.isin(lab, [i for i in range(1, n) if st[i, 4] >= min_area]).astype(np.uint8)
    grow = max(3, pano.shape[1] // 68) | 1
    return cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow, grow)))


def fill_from_side(pano, mask):
    """Replace each masked blob with floor from the same rows, shifted sideways to the flattest spot."""
    out = pano.copy()
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask)
    edges = cv2.Laplacian(cv2.GaussianBlur(cv2.cvtColor(pano, cv2.COLOR_BGR2GRAY), (0, 0), 2), cv2.CV_32F)
    for i in range(1, n):
        x, y, w, h, _ = st[i]
        blob = (lab == i).astype(np.uint8) * 255
        best = None
        for k in (1, -1, 2, -2, 3, -3):
            shift = k * (w + w // 3)
            moved = np.roll(blob, shift, axis=1) > 0
            if (moved & (mask > 0)).any():
                continue
            cost = np.abs(np.roll(edges, -shift, axis=1)[blob > 0]).mean()
            if best is None or cost < best[0]:
                best = (cost, shift)
        if best is None:
            continue
        donor = np.roll(out, -best[1], axis=1)
        out = cv2.seamlessClone(donor, out, blob, (int(x + w // 2), int(y + h // 2)), cv2.NORMAL_CLONE)
        print("filled feet blob %d (%dx%d px) from %+d px sideways" % (i, w, h, best[1]))
    return out

ap = argparse.ArgumentParser()
ap.add_argument("out", nargs="?", default="output_images/improved_panorama.jpg")
ap.add_argument("--width", type=int, default=ps.OUT_W)
ap.add_argument("--scale", type=float, default=ps.SCALE)
ap.add_argument("--nadir-weight", type=float, default=0.0001, help="seam weight of the nadir shot (1 = unchanged)")
ap.add_argument("--zenith-weight", type=float, default=3.0, help="seam weight of the zenith shot (1 = unchanged)")
ap.add_argument("--keep-feet", action="store_true", help="skip the feet clean-up")
a = ap.parse_args()
ps.SCALE = a.scale
os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

shots, heading = ps.load_shots()
shots = ps.apply_corrections(shots)
for s in shots:
    if s["name"] == "nadir":
        s["qw"] *= a.nadir_weight
    if s["name"] == "zenith":
        s["qw"] *= a.zenith_weight
center = heading if ps.CENTER_AZ is None else ps.CENTER_AZ
pano, covered, count = ps.render(shots, a.width, ps.focal(), center)
if not a.keep_feet:
    pano = fill_from_side(pano, feet_mask(pano, nadir_only(shots, a.width, center, ps.focal())))
cv2.imwrite(a.out, pano, [cv2.IMWRITE_JPEG_QUALITY, 92])
print("saved", a.out, pano.shape)
ps.report(covered, count, shots)
