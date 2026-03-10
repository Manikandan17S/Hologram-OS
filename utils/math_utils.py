import math
import numpy as np

def calculate_distance(p1, p2):
    """Calculates Euclidean distance between two points (x, y)."""
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def map_range(value, in_min, in_max, out_min, out_max):
    """Maps a value from one range to another."""
    return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def normalize_landmarks(landmarks, width, height):
    """Converts normalized MediaPipe landmarks to pixel coordinates."""
    pixel_landmarks = []
    for lm in landmarks:
        pixel_landmarks.append((int(lm.x * width), int(lm.y * height)))
    return pixel_landmarks
