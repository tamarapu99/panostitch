import cv2
from stitching import Stitcher
import glob
import os
import re

# Load images
image_paths = glob.glob("multiple_input/*.jpg") + \
              glob.glob("multiple_input/*.jpeg")

# Natural sorting
image_paths = sorted(
    image_paths,
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

print("Images loaded:", len(images))

if len(images) < 2:
    raise ValueError("Please add at least two images.")

# Create OpenStitching engine
stitcher = Stitcher()

# Stitch images
panorama = stitcher.stitch(images)

# Save result
os.makedirs("output_images", exist_ok=True)

cv2.imwrite(
    "output_images/openstitching_panorama.jpg",
    panorama
)

print("Panorama saved successfully!")