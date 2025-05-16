from grasper import AutograsperBase
from library.utils import OrderType
from library.rgb_object_tracker import get_object_pos, cam_to_robot
import time
import numpy as np
from typing import List, Tuple
import cv2
import os
import sys
import random

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.append(project_root)

from client.cloudgripper_client import GripperRobot
from library.utils import convert_ndarray_to_list, get_undistorted_bottom_image
from file_manager import FileManager


def find_object(
    image,
    lower_color,
    upper_color,
    shape="any",
    min_size=100,
    max_size=None,
    circularity_threshold=0.8,
    output_path=None,
    show_mask=False,
):
    """
    Find an object in an image based on color range, size constraints, and shape,
    with robustness against noise and fragmentation.

    Parameters:
    -----------
    image : numpy.ndarray
        OpenCV image object (BGR format)
    lower_color : tuple
        Lower bound of color range in HSV format (hue, saturation, value)
    upper_color : tuple
        Upper bound of color range in HSV format (hue, saturation, value)
    shape : str
        Shape to detect: "circle", "rectangle", or "any"
    min_size : int
        Minimum area of the object in pixels
    max_size : int or None
        Maximum area of the object in pixels, if None, no maximum size limit
    circularity_threshold : float
        Threshold for circle detection (0-1, higher is more strict)
    output_path : str or None
        Path to save the output image with marked object
    show_mask : bool
        If True, returns a masked image showing only colors in the specified range

    Returns:
    --------
    tuple
        (center_coordinates, output_image, mask_image)
        center_coordinates: (x, y) coordinates or None if no object found
        output_image: image with red dot at object center
        mask_image: image showing only the colors in range (if show_mask=True, else None)
    """
    if image is None or image.size == 0:
        raise ValueError("Invalid image input")

    # Make a copy for drawing
    output_image = image.copy()

    # Convert to HSV color space
    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Create a mask based on the color range
    mask = cv2.inRange(hsv_image, np.array(lower_color), np.array(upper_color))

    # Apply morphological operations to clean up the mask
    # 1. Remove small noise with opening (erosion followed by dilation)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # 2. Close gaps within objects with closing (dilation followed by erosion)
    kernel = np.ones((15, 15), np.uint8)  # Larger kernel to close bigger gaps
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # Optional: Apply Gaussian blur to smooth the mask edges
    mask = cv2.GaussianBlur(mask, (5, 5), 0)

    # Re-threshold after blurring to get a binary mask again
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    # Find contours in the cleaned mask
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    center_coordinates = None

    # Filter contours based on size and shape constraints
    valid_contours = []
    for contour in contours:
        area = cv2.contourArea(contour)

        # Size filter
        if area < min_size or (max_size is not None and area > max_size):
            continue

        # Shape filter
        if shape.lower() == "circle":
            # Calculate circularity (4*pi*area/perimeter^2)
            perimeter = cv2.arcLength(contour, True)
            if perimeter == 0:
                continue

            circularity = 4 * np.pi * area / (perimeter * perimeter)

            # Circles have circularity close to 1
            if circularity < circularity_threshold:
                continue

        elif shape.lower() == "rectangle":
            # Calculate how rectangular the shape is
            x, y, w, h = cv2.boundingRect(contour)
            rect_area = w * h
            extent = float(area) / rect_area

            # Rectangles have high extent (area ratio)
            if extent < 0.7:  # Threshold for rectangularity
                continue

        # If we got here, the contour passes all filters
        valid_contours.append(contour)

    # Process if valid contours found
    if valid_contours:
        # Find the largest valid contour
        largest_contour = max(valid_contours, key=cv2.contourArea)

        # Calculate the center of the contour
        M = cv2.moments(largest_contour)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            center_coordinates = (cx, cy)

            # Draw a red dot at the center of the object
            cv2.circle(output_image, center_coordinates, 10, (0, 0, 255), -1)

            # Optionally draw the contour
            cv2.drawContours(output_image, [largest_contour], 0, (0, 255, 0), 2)

    # Create mask visualization if requested
    mask_image = None
    if show_mask:
        # Create a color representation of the mask for visualization
        mask_rgb = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        # Apply the mask to the original image
        original_masked = cv2.bitwise_and(image, image, mask=mask)
        # Combine for visualization (left half: masked original, right half: mask)
        h, w = mask.shape[:2]
        mask_image = np.zeros((h, w, 3), dtype=np.uint8)
        mask_image[:, : w // 2] = original_masked[:, : w // 2]
        mask_image[:, w // 2 :] = mask_rgb[:, w // 2 :]

    # Save the output image if path provided
    if output_path is not None and center_coordinates is not None:
        cv2.imwrite(output_path, output_image)
        print(f"Image with marked object saved to {output_path}")

    return (center_coordinates, output_image, mask_image)


def create_color_mask_with_cleanup(
    image,
    lower_color,
    upper_color,
    noise_kernel_size=5,
    gap_kernel_size=15,
    blur_kernel_size=5,
    output_path=None,
):
    """
    Create a cleaned mask showing colors within the specified range with noise reduction.

    Parameters:
    -----------
    image : numpy.ndarray
        OpenCV image object (BGR format)
    lower_color : tuple
        Lower bound of color range in HSV format (hue, saturation, value)
    upper_color : tuple
        Upper bound of color range in HSV format (hue, saturation, value)
    noise_kernel_size : int
        Size of kernel for noise removal (opening operation)
    gap_kernel_size : int
        Size of kernel for gap filling (closing operation)
    blur_kernel_size : int
        Size of kernel for Gaussian blur smoothing
    output_path : str or None
        Path to save the mask image

    Returns:
    --------
    numpy.ndarray
        Binary mask image with noise reduction
    """
    if image is None or image.size == 0:
        raise ValueError("Invalid image input")

    # Convert to HSV color space
    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Create a mask based on the color range
    mask = cv2.inRange(hsv_image, np.array(lower_color), np.array(upper_color))

    # Apply morphological operations to clean up the mask
    # 1. Remove small noise with opening (erosion followed by dilation)
    noise_kernel = np.ones((noise_kernel_size, noise_kernel_size), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, noise_kernel)

    # 2. Close gaps within objects with closing (dilation followed by erosion)
    gap_kernel = np.ones((gap_kernel_size, gap_kernel_size), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, gap_kernel)

    # Optional: Apply Gaussian blur to smooth the mask edges
    if blur_kernel_size > 0:
        mask = cv2.GaussianBlur(mask, (blur_kernel_size, blur_kernel_size), 0)
        # Re-threshold after blurring to get a binary mask again
        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    # Save the mask image if path provided
    if output_path is not None:
        cv2.imwrite(output_path, mask)
        print(f"Cleaned mask image saved to {output_path}")

    return mask


class BackgammonGrasper(AutograsperBase):
    def __init__(self, config, shutdown_event, task: str):
        super().__init__(config, shutdown_event=shutdown_event)
        self.task = task
        self.reset_position = [0.1, 0.8]
        self.start_position_gripper = [0.0, 1.0]
        self.camera_matrix = config["camera"]["m"]
        self.distortion_coeffs = config["camera"]["d"]

    def center_sweep(self):
        orders = [
            (OrderType.GRIPPER_CLOSE, [0]),
            (OrderType.MOVE_Z, [0]),
            (OrderType.MOVE_XY, [0.5, 0.0]),
            (OrderType.MOVE_XY, [0.5, 0.4]),
            (OrderType.MOVE_XY, [0.5, 0.5]),
            (OrderType.MOVE_XY, [0.5, 0.6]),
            (OrderType.MOVE_XY, [0.4, 0.6]),
            (OrderType.MOVE_XY, [0.4, 0.4]),
            (OrderType.MOVE_XY, [0.6, 0.4]),
        ]
        self.queue_robot_orders(orders, delay=self.time_between_orders)

    def get_color_pos(self, color):
        return get_object_pos(self.bottom_image, self.robot_idx, color)

    def check_grasping_success(self):
        state = self.robot_state

        gripper_pos = [state["x_norm"], state["y_norm"]]

        object_position = self.get_colod_pos("green")

        if object_position is None:
            return False

        gripper_is_close_enough = (
            np.linalg.norm(np.array(gripper_pos) - np.array(object_position)) < 0.10
        )

        return gripper_is_close_enough

    def find_disc(self, lower=None, upper=None):
        if self.bottom_image is None:
            self.bottom_image = get_undistorted_bottom_image(
                self.robot, self.camera_matrix, self.distortion_coeffs
            )

        image = self.bottom_image

        if lower is None or upper is None:
            lower = (0, 0, 0)
            upper = (360, 100, 60)
        lower_color = lower
        upper_color = upper

        test1 = create_color_mask_with_cleanup(
            image,
            lower_color,
            upper_color,
            noise_kernel_size=3,  # Smaller kernel for less aggressive noise removal
            gap_kernel_size=7,  # Smaller kernel for less gap filling
            output_path="mask_mild_cleanup.jpg",
        )

        test2 = create_color_mask_with_cleanup(
            image,
            lower_color,
            upper_color,
            noise_kernel_size=2,  # Medium noise removal
            gap_kernel_size=5,  # Medium gap filling
            output_path="mask_medium_cleanup.jpg",
        )

        test3 = create_color_mask_with_cleanup(
            image,
            lower_color,
            upper_color,
            noise_kernel_size=3,  # Stronger noise removal
            gap_kernel_size=2,  # Stronger gap filling
            output_path="mask_strong_cleanup.jpg",
        )

        center, marked_image, mask_image = find_object(
            image,
            lower_color,
            upper_color,
            shape="circle",
            circularity_threshold=0.7,
            min_size=100,
            output_path="detected_circle.jpg",
            show_mask=True,
        )

        # Save the mask image showing only the colors in range

        object_robot_coordinates = cam_to_robot(self.robot_idx, center)
        return object_robot_coordinates

    def pick_and_place_disc(self, target_position):
        disc_position = self.find_disc()
        if disc_position:
            self.pick_and_place_object(
                disc_position, 0, 0, target_position=target_position
            )
        else:
            print("No object found matching the criteria")

    def perform_task(self):
        if self.task == "pick-and-place":
            target_pos = [0.2, 0.2]
            if random.random() > 0.5:
                rand_x = np.random.uniform(0.2, 0.8)
                rand_y = np.random.uniform(0.2, 0.8)
                target_pos = [rand_x, rand_y]

            self.pick_and_place_disc(target_pos)

    def reset_task(self):
        time.sleep(1)
        return
        rand_x = np.random.uniform(0.2, 0.8)
        rand_y = np.random.uniform(0.2, 0.8)

        self.pick_and_place_disc([rand_x, rand_y])

        return

    def startup(self):
        orders = [
            (OrderType.GRIPPER_OPEN, []),
            (OrderType.MOVE_Z, [1]),
            (OrderType.MOVE_XY, self.start_position_gripper),
            (OrderType.GRIPPER_CLOSE, []),
        ]
        self.queue_orders(orders, time_between_orders=self.time_between_orders)
        return

    def pick_and_place_object(
        self,
        object_position: Tuple[float, float],
        object_height: float,
        target_height: float,
        target_position: List[float] = [0.5, 0.5],
    ):
        orders = [
            (OrderType.GRIPPER_OPEN, []),
            (OrderType.MOVE_Z, [1]),
            (OrderType.MOVE_XY, object_position),
            (OrderType.MOVE_Z, [object_height]),
            (OrderType.GRIPPER_CLOSE, []),
            (OrderType.MOVE_Z, [1]),
            (OrderType.MOVE_XY, target_position),
            (OrderType.MOVE_Z, [target_height]),
            (OrderType.GRIPPER_OPEN, []),
        ]
        self.queue_orders(orders, time_between_orders=self.time_between_orders)
