"""Refine per-shot rotations (and a shared focal length) from feature matches.

Starts from the device poses, matches SIFT features between shots that overlap,
keeps matches consistent with the pose prior, then minimises the angular distance
between matched rays with a robust loss. Writes pose_corrections.json (axis-angle
corrections applied on the left of the device rotation) and the refined focal.
"""
import json
import itertools

import cv2
import numpy as np
from scipy.optimize import least_squares

import pose_stitch as ps

MAX_SEP_DEG = 75       # only match shots whose optical axes are this close
PRIOR_ERR_DEG = 12     # reject matches that disagree with the pose prior by more
PRIOR_WEIGHT = 0.15    # soft pull of corrections toward zero (per radian, in px units)


def ray(R, pts, f, w, h):
    x = pts[:, 0] - w / 2
    y = pts[:, 1] - h / 2
    v = np.stack([x / f, -y / f, -np.ones(len(pts))], 1)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    return v @ R.T


def main():
    shots, _ = ps.load_shots()
    f0 = ps.focal()
    n = len(shots)
    sift = cv2.SIFT_create(6000)
    feats = []
    for s in shots:
        g = cv2.cvtColor(s["img"], cv2.COLOR_BGR2GRAY)
        g = cv2.createCLAHE(2.0, (8, 8)).apply(g)
        kp, d = sift.detectAndCompute(g, None)
        feats.append((np.array([k.pt for k in kp], np.float32), d))
    h, w = shots[0]["img"].shape[:2]
    axes = [s["R"] @ np.array([0, 0, -1.0]) for s in shots]
    bf = cv2.BFMatcher()
    raw = []
    for i, j in itertools.combinations(range(n), 2):
        if np.degrees(np.arccos(np.clip(axes[i] @ axes[j], -1, 1))) > MAX_SEP_DEG:
            continue
        m = bf.knnMatch(feats[i][1], feats[j][1], k=2)
        good = [a for a, b in (x for x in m if len(x) == 2) if a.distance < 0.8 * b.distance]
        if len(good) < 15:
            continue
        raw.append((i, j, feats[i][0][[g.queryIdx for g in good]], feats[j][0][[g.trainIdx for g in good]]))
    print(f"{len(raw)} candidate pairs")

    R0 = [s["R"] for s in shots]
    x = np.zeros(3 * n + 1)
    x[-1] = 1.0

    def unpack(x):
        return x[: 3 * n].reshape(n, 3), x[3 * n]

    def current_Rs(x):
        rv, _ = unpack(x)
        return [cv2.Rodrigues(rv[k])[0] @ R0[k] for k in range(n)]

    def select(x, thresh_deg):
        _, fs = unpack(x)
        Rs = current_Rs(x)
        obs = []
        for i, j, pi, pj in raw:
            ri = ray(Rs[i], pi, f0 * fs, w, h)
            rj = ray(Rs[j], pj, f0 * fs, w, h)
            ang = np.degrees(np.arccos(np.clip((ri * rj).sum(1), -1, 1)))
            keep = ang < thresh_deg
            if keep.sum() >= 12:
                obs.append((i, j, pi[keep], pj[keep]))
        return obs

    def make_res(obs):
        def residuals(x):
            rv, fs = unpack(x)
            f = f0 * fs
            Rs = current_Rs(x)
            res = []
            for i, j, pi, pj in obs:
                res.append((ray(Rs[i], pi, f, w, h) - ray(Rs[j], pj, f, w, h)).ravel() * f)
            res.append(rv.ravel() * PRIOR_WEIGHT * f)
            res.append([(fs - 1) * 5 * f])
            return np.concatenate(res)
        return residuals

    for thresh in (12, 6, 3, 1.5):
        obs = select(x, thresh)
        res = make_res(obs)
        sol = least_squares(res, x, loss="huber", f_scale=3.0, max_nfev=40)
        x = sol.x
        rv, fs = unpack(x)
        nm = sum(len(o[2]) for o in obs)
        print(f"thresh {thresh:>4} deg: {len(obs)} pairs, {nm} matches, rms {np.sqrt(np.mean(sol.fun**2)):.2f}px, focal {ps.FOCAL_PX_FULL*fs:.0f}")

    obs = select(x, 3)
    Rs = current_Rs(x)
    _, fs = unpack(x)
    print("per-pair median error (px, half-res), worst 8:")
    errs = []
    for i, j, pi, pj in obs:
        e = np.linalg.norm(ray(Rs[i], pi, f0 * fs, w, h) - ray(Rs[j], pj, f0 * fs, w, h), axis=1) * f0 * fs
        errs.append((np.median(e), shots[i]["name"], shots[j]["name"], len(e)))
    for e in sorted(errs, reverse=True)[:8]:
        print("  %.1f  %s - %s (%d)" % e)
    # remove the free global rotation: rotate the solution back as close to the device poses as possible
    Rs = current_Rs(x)
    M = sum(R0[k] @ Rs[k].T for k in range(n))
    U, _, Vt = np.linalg.svd(M)
    G = U @ np.diag([1, 1, np.linalg.det(U @ Vt)]) @ Vt
    rv = np.array([cv2.Rodrigues(G @ Rs[k] @ R0[k].T)[0].ravel() for k in range(n)])
    _, fs = unpack(x)
    print("max correction deg: %.2f" % np.degrees(np.abs(rv).max()))
    json.dump({"focal_scale": float(fs), **{shots[k]["name"]: rv[k].tolist() for k in range(n)}},
              open(ps.CORR_FILE, "w"), indent=1)


if __name__ == "__main__":
    main()
