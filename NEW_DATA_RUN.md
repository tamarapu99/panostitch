# PanoStitch: running the new dataset (Outside room)

Date of run: 4 Nov 2026. This document records how the new capture was checked and run
with the existing PanoStitch pipeline, what came out, and what to watch for.

---

## 1. Summary

- The new capture came from a different phone (Samsung) than the living-room data (Redmi).
- The **Outside** room was run through the **same, unchanged scripts**: `refine_poses.py`,
  `pose_stitch.py` and `improve_pano.py`. No script was edited or copied.
- It produced a full 360° panorama with 100% coverage and a final match error of about 9.6 px.
- **Room 1** and **Room 2** were also run with the same scripts (plain and improved versions).
  Their printed numbers (error, coverage, overlap) were not recorded in this document.
  **Bathroom** cannot be run: its photos are missing from the folder.
- Results were judged by the printed numbers and by looking at the images at reduced size.

---

## 2. The data that was provided

Folder: `new_capture/capture-1793689191496-home-mw0bhuhj-3bid/`

| Item | Value |
| --- | --- |
| Format | `conceptdash.capture/2`, guided capture |
| Home name | Construction site, 1 floor |
| Phone | Samsung SM-S938B, Android 16 |
| Photo size | 3060 x 4080, JPEG (same as the living-room data) |
| EXIF in the photos | None (checked on the first photo of each room that is on disk) |
| Files | `home.json`, `export.json`, `README.txt`, room folders |

### Rooms listed in `home.json`

| Room | Photos on disk | Poses present | Sharpness (min / median / max) | Brightness range |
| --- | --- | --- | --- | --- |
| Outside | 30 | all 30 | 52 / 773 / 1609 | 107 to 156 |
| Room 1 | 30 | all 30 | 2 / 113 / 1160 | 87 to 171 |
| Room 2 | 30 | all 30 | 49 / 233 / 1790 | 82 to 167 |
| Bathroom | **0 (folder missing)** | all 30 listed | 1 / 29 / 619 | 116 to 170 |

For comparison, the living-room data had a median sharpness of about 1045.

`export.json` lists all four rooms as complete with no missing targets, even though the
Bathroom photos are not in the folder.

### Things found during the check

1. Everything sits one folder deeper than expected, inside the `capture-...` folder.
2. The Bathroom photos are not on disk.
3. The scripts read only the **first** room in `home.json`, which here is **Outside**.
4. Low sharpness scores in Room 1, Room 2 and Bathroom. These may reflect plain, textureless
   walls instead of real blur. That was not checked.

---

## 3. How it was run

### Idea
The scripts find their data relative to the folder they are started from (`captured_input/`
and `pose_corrections.json`). So the project's own scripts were run from a **separate working
folder** in which `captured_input` is a link to the new capture folder. This keeps the
living-room data and its `pose_corrections.json` untouched, and stops old corrections being
applied to the new photos.

### Steps

| # | Step | Notes |
| --- | --- | --- |
| 1 | Read `home.json` and `export.json` | Schema, rooms, shots, poses, photo sizes, files on disk |
| 2 | Create a working folder with `captured_input` linked to the capture folder | The Outside room is first in `home.json`, so the original file is used as is |
| 3 | `refine_poses.py` | Corrects each photo's angle and the shared focal length using SIFT matches |
| 4 | `pose_stitch.py plain.jpg` | The plain stitch, using the corrections from step 3 |
| 5 | `improve_pano.py improved.jpg` | The stitch with the straight-down photo almost ignored, the straight-up photo weighted x3, and the feet clean-up |
| 6 | Copy the results to `output_images/` as new files | `outside_plain.jpg`, `outside_improved.jpg` |
| 7 | Check that no existing file changed | Modification times of the scripts, `pose_corrections.json` and the living-room images |

The run used the project's own Python environment (`.venv`).

### Commands to repeat it yourself

Run these from the project folder. They are equivalent to what was run (the original run
used absolute paths).

```bash
cd /Users/charan/Documents/PanoStitch
source .venv/bin/activate

mkdir -p runs/outside && cd runs/outside
ln -s ../../new_capture/capture-1793689191496-home-mw0bhuhj-3bid captured_input

python ../../refine_poses.py          # writes pose_corrections.json in this folder
python ../../pose_stitch.py plain.jpg
python ../../improve_pano.py improved.jpg
```

To view the result:

```bash
cd /Users/charan/Documents/PanoStitch
python -m http.server 8000
# open: http://localhost:8000/walkthrough.html?img=output_images/outside_improved.jpg
```

Without `?img=...` the viewer shows its default image (`test_v2.jpg`, the living room).

### Running another room (done for Room 1 and Room 2)
The scripts read only the first room. For Room 1 or Room 2, make a copy of `home.json` that
lists only that room, put it in a folder with a link to that room's photo folder, and link
`captured_input` to that folder. This copies data only, not the scripts.

---

## 4. Results (Outside room)

### Angle refinement (`refine_poses.py`)

| Round | Pairs | Matches | Error | Focal length |
| --- | --- | --- | --- | --- |
| limit 12 deg | 86 | 28244 | 24.7 px | 2932 |
| limit 6 deg | 83 | 27794 | 19.1 px | 2933 |
| limit 3 deg | 78 | 26510 | 12.9 px | 2925 |
| limit 1.5 deg | 75 | 24162 | 9.6 px | 2928 |

151 candidate photo pairs in total. The largest single angle component corrected was 26.5 deg.

Worst pairs (median error, half-resolution px): level-7 / down-3 52.6, down-7 / nadir 45.9,
level-10 / down-5 45.6, down-0 / nadir 44.9, down-5 / down-6 42.5.

### Stitch report

| Check | Value |
| --- | --- |
| Coverage | 100% |
| Overlap of 2+ photos | 80.7% |
| Zenith / up / level / down / nadir overlap | 82.1% / 96.7% / 93.2% / 79.5% / 43.2% |
| Pose corrections | mean 8.2 deg, max 31.2 deg, focal scale 0.955 |
| Brightness gains | at their limits (0.78 to 1.28) |
| Output size | 4096 x 2048 |

### Compared with the living-room run

| | Outside | Living room |
| --- | --- | --- |
| Final match error | 9.6 px | 10.3 px |
| Focal length found | about 2928 | about 3124 |
| Mean / max angle correction | 8.2 / 31.2 deg | 7.7 / 11.5 deg |
| Nadir overlap | 43.2% | 32.1% |

### What the images show
- A full 360° panorama of the building, trees, sky and excavations, with no obvious doubled
  objects or visible seams at the viewed size.
- The photographer's white sandals show at the bottom left and right of the plain version.
  The improved version removes most of them, but faint grey outlines remain.
- The stretched bottom edge is normal for a 360° image.
- Images were only viewed at reduced size.

### Output files
- `output_images/outside_plain.jpg`
- `output_images/outside_improved.jpg`

### Room 1 and Room 2
Both rooms were run the same way as Outside (same unchanged scripts, a separate working
folder, `home.json` copy listing only that room). The results were saved as new files:

| Room | Plain | Improved |
| --- | --- | --- |
| Room 1 | `output_images/room1_plain.jpg` | `output_images/room1_improved.jpg` |
| Room 2 | `output_images/room2_plain.jpg` | `output_images/room2_improved.jpg` |

Not recorded here: the final match error, coverage, overlap and pose-correction numbers for
these two rooms. Room 1 and Room 2 had low sharpness scores in the data check (Room 1 median
113, Room 2 median 233, against 773 for Outside), so check their results with that in mind.

To view them:
`http://localhost:8000/walkthrough.html?img=output_images/room1_improved.jpg` (or `room2_improved.jpg`).

---

## 5. Points to watch

1. **Max correction of 31 deg.** Large. The final error is small and the picture looks
   aligned, but which shot needed it and why was not investigated.
2. **Different focal length (about 2928 vs 3124).** Consistent with a different phone. The
   starting guess (3065 px) was left unchanged and the refine step adjusted it.
3. **Improved version is tuned to the living room.** The weights (straight-down photo almost
   ignored, straight-up photo x3) and the colour-based feet clean-up were chosen while looking
   at that room. They worked here, but this is not guaranteed on other data. The feet clean-up
   could paint over coloured objects on the ground.
4. **Brightness gains at their limit** in both datasets, so brightness matching may be cut off.
5. **Low sharpness in Room 1, Room 2 and Bathroom.** Expect weaker results there.
6. **No EXIF in any photo.** The real focal length, exposure and lens data are not available.

---

## 6. Not done

- Room 1 and Room 2 were not run.
- Bathroom cannot be run until its photos are added to the folder.
- No pipeline file was changed.

## 7. Files that were not changed

`pose_stitch.py`, `refine_poses.py`, `improve_pano.py`, `pose_corrections.json`,
`output_images/pose_panorama.jpg` and `output_images/improved_panorama.jpg` kept their earlier
modification times after the run.
