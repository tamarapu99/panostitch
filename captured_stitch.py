import cv2
import glob
import os
import re

# STEP 1: Load the 30 captured images
input_folder = "captured_input/room-mw0f38sm-xih8"

image_paths = sorted(
    glob.glob(os.path.join(input_folder, "*.jpg")) +
    glob.glob(os.path.join(input_folder, "*.jpeg")),
    key=lambda path: int(
        re.search(r"shot-(\d+)", os.path.basename(path)).group(1)
    )
)

images = []

for path in image_paths:
    image = cv2.imread(path)

    if image is not None:
        images.append(image)

print("Number of images loaded:", len(images))
print("Image order:")

for path in image_paths:
    print(os.path.basename(path))

if len(images) < 2:
    raise ValueError("At least 2 images are required.")

# STEP 2: Create the OpenCV stitcher
stitcher = cv2.Stitcher_create()

# STEP 3: Stitch all 30 images
print("\nStarting stitching of captured images...")

status, panorama = stitcher.stitch(images)

print("Stitching status:", status)

# STEP 4: Save the panorama
output_folder = "output_images"
os.makedirs(output_folder, exist_ok=True)

if status == cv2.Stitcher_OK:
    output_path = os.path.join(
        output_folder,
        "captured_30_panorama.jpg"
    )

    cv2.imwrite(output_path, panorama)

    print("Panorama saved:", output_path)
    print("Panorama dimensions:", panorama.shape[1], "x", panorama.shape[0])

else:
    print("Stitching failed. OpenCV status:", status)