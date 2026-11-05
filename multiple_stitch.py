import cv2
import numpy as np
import glob
import os

# STEP 1: Load all images
import re

image_paths = sorted(
    glob.glob("captured_input/room-mw0f38sm-xih8/*.jpg") +
    glob.glob("captured_input/room-mw0f38sm-xih8/*.jpeg"),
    key=lambda path: [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", os.path.basename(path))
    ]
)

images = []

for path in image_paths:
    image = cv2.imread(path)

    if image is not None:
        images.append(image)

print("Number of images loaded:", len(images))
print("Image order:", [os.path.basename(path) for path in image_paths])

if len(images) < 2:
    raise ValueError("Please add at least 2 JPG images to multiple_input.")

# STEP 2: Create the stitcher
stitcher = cv2.Stitcher_create()

# STEP 3: Stitch all images
os.makedirs("output_images", exist_ok=True)

groups = {
    "panorama_1_5.jpg": images[:5],
    "panorama_6_10.jpg": images[-5:]
}

for filename, group in groups.items():
    stitcher = cv2.Stitcher_create()
    status, panorama = stitcher.stitch(group)

    print(filename, "Status:", status)

    if status == cv2.Stitcher_OK:
        cv2.imwrite(
            os.path.join("output_images", filename),
            panorama
        )
        print("Saved:", filename)
    else:
        print("Stitching failed:", filename)