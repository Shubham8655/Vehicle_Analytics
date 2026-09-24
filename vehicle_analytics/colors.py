"""Lightweight dominant vehicle body color estimate using HSV pixels."""

from __future__ import annotations

import cv2
import numpy as np


def classify_color(crop: np.ndarray) -> str:
    """Return a coarse color label from a BGR vehicle crop."""
    if crop.size == 0:
        return "unknown"
    height, width = crop.shape[:2]
    # The central region reduces road, shadow, glass, and background influence.
    region = crop[int(height * 0.2):max(int(height * 0.8), 1), int(width * 0.2):max(int(width * 0.8), 1)]
    if region.size == 0:
        region = crop
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    pixels = hsv.reshape(-1, 3)
    useful = pixels[(pixels[:, 2] > 30)]
    if len(useful) == 0:
        return "black"
    saturation = useful[:, 1]
    if float(np.median(saturation)) < 38:
        brightness = float(np.median(useful[:, 2]))
        return "white" if brightness > 190 else "silver" if brightness > 135 else "gray" if brightness > 75 else "black"
    chromatic = useful[saturation > 45]
    if len(chromatic) == 0:
        return "gray"
    hue = int(np.median(chromatic[:, 0]))
    if hue < 8 or hue >= 170:
        return "red"
    if hue < 20:
        return "orange"
    if hue < 35:
        return "yellow"
    if hue < 85:
        return "green"
    if hue < 130:
        return "blue"
    return "purple"
