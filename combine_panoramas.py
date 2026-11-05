import cv2
import os

# Load the two existing panoramas
panorama1 = cv2.imread("output_images/panorama_1_5.jpg")
panorama2 = cv2.imread("output_images/panorama_6_10.jpg")

if panorama1 is None or panorama2 is None:
    raise ValueError("Could not load both panorama images.")

# Create OpenCV stitcher
stitcher = cv2.Stitcher_create()

# Combine both panoramas
status, final_panorama = stitcher.stitch([panorama1, panorama2])

print("Stitching status:", status)

if status == cv2.Stitcher_OK:
    cv2.imwrite(
        "output_images/final_panorama.jpg",
        final_panorama
    )
    print("Final panorama saved successfully!")
else:
    print("Could not connect the two panoramas.")