# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import datetime
import json
import os
import uuid
from typing import Sequence


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
from scipy.spatial import ConvexHull


# FUNCTION DEFINITIONS --------------------------------------------------------

# GENERAL UTILITIES ///////////////////////////////////////////////////////////

def sanitize_path(fp: str = ''):
    """Sanitizes a filepath an returns the result."""
    return os.path.abspath(os.path.realpath(os.path.normpath(fp)))


def slash_join(*args):
    """Joins together a bunch of strings using slashes."""
    return '/'.join(arg.strip('/') for arg in args)


def validate_uuid(uuid_to_test: str, version: int = 4):
    """
    Check if uuid_to_test is a valid UUID.

    Parameters
    ----------
    uuid_to_test : str
    version : {1, 2, 3, 4}

    Returns
    -------
    True if uuid_to_test is a valid UUID, otherwise False.
    """
    try:
        uuid_obj = uuid.UUID(uuid_to_test, version=version)
    except ValueError:
        return False
    return str(uuid_obj) == uuid_to_test


def sort_pts(points: Sequence[Sequence[float]]):
    """
    Sorts (x, y) points in clockwise order.
    """
    sorted_pts = np.zeros((4, 2), dtype='float32')
    s = np.sum(points, axis=1)
    sorted_pts[0] = points[np.argmin(s)]
    sorted_pts[2] = points[np.argmax(s)]
    diff = np.diff(points, axis=1)
    sorted_pts[1] = points[np.argmin(diff)]
    sorted_pts[3] = points[np.argmax(diff)]
    return sorted_pts


def minimum_bounding_rectangle(points):
    hull = ConvexHull(points)
    hull_points = points[hull.vertices]
    min_area = float('inf')
    best_rectangle = None
    best_angle = 0

    for i in range(len(hull_points)):
        p1 = hull_points[i]
        p2 = hull_points[(i + 1) % len(hull_points)]
        edge_vec = p2 - p1
        angle = np.arctan2(edge_vec[1], edge_vec[0])
        cos_angle = np.cos(-angle)
        sin_angle = np.sin(-angle)
        rot_matrix = np.array([[cos_angle, -sin_angle],
                               [sin_angle, cos_angle]])
        rotated_points = np.dot(points, rot_matrix.T)
        min_x = np.min(rotated_points[:, 0])
        max_x = np.max(rotated_points[:, 0])
        min_y = np.min(rotated_points[:, 1])
        max_y = np.max(rotated_points[:, 1])
        area = (max_x - min_x) * (max_y - min_y)
        if area < min_area:
            min_area = area
            best_angle = angle
            best_rectangle = np.array([
                [min_x, min_y],
                [max_x, min_y],
                [max_x, max_y],
                [min_x, max_y]
            ])
            inv_rot_matrix = np.array([[cos_angle, sin_angle],
                                       [-sin_angle, cos_angle]])
            best_rectangle = np.dot(best_rectangle, inv_rot_matrix.T)

    return best_rectangle, best_angle


def align_and_translate_mbr(points, rectangle, angle):
    cos_angle = np.cos(-angle)
    sin_angle = np.sin(-angle)
    rotation_matrix = np.array([[cos_angle, -sin_angle],
                                [sin_angle, cos_angle]])
    rotated_rectangle = np.dot(rectangle, rotation_matrix.T)
    rotated_points = np.dot(points, rotation_matrix.T)
    # Calculate dimensions to determine the longer side
    width = np.max(rotated_rectangle[:, 0]) - np.min(rotated_rectangle[:, 0])
    height = np.max(rotated_rectangle[:, 1]) - np.min(rotated_rectangle[:, 1])
    # Ensure the long side is aligned with the x-axis
    if height > width:
        # Rotate by 90 degrees
        additional_rotation = np.array([[0, -1], [1, 0]])
        rotated_rectangle = np.dot(rotated_rectangle, additional_rotation.T)
        rotated_points = np.dot(rotated_points, additional_rotation.T)
    # Translate so the rectangle's lower-left corner is at the origin
    min_x, min_y = rotated_rectangle.min(axis=0)
    rect_center = (np.max(rotated_rectangle, axis=0) +
                   np.min(rotated_rectangle, axis=0)) / 2
    translated_rectangle = rotated_rectangle - rect_center
    translated_points = rotated_points - rect_center
    # Reorder the rectangle points to maintain the consistent order
    ordered_rectangle = np.array([
        [np.min(translated_rectangle[:, 0]),
         np.min(translated_rectangle[:, 1])],
        [np.max(translated_rectangle[:, 0]),
         np.min(translated_rectangle[:, 1])],
        [np.max(translated_rectangle[:, 0]),
         np.max(translated_rectangle[:, 1])],
        [np.min(translated_rectangle[:, 0]),
         np.max(translated_rectangle[:, 1])]
    ])
    return translated_points, ordered_rectangle


def polygon_np_xy(contour_points: np.array) -> np.array:
    """
    Return a np array of [x, y] points of the input contour points.
    """
    polygon_pts = [(float(pt[0][0]), float(pt[0][1])) for pt in contour_points]
    polygon_pts.append(polygon_pts[0])
    polygon_pts = np.array(polygon_pts)
    return polygon_pts


def load_json_sheet(fp: str):
    """
    Load .JSON file containing a sheet description
    """
    json_object = None
    with open(fp, 'r') as sheet:
        # Reading from json file
        json_object = json.load(sheet)
    # return JSON dict
    return json_object


def create_timestamp_str():
    """
    Creates a timestamp in YYMMDD-HHMMSS format.
    """
    timestamp = datetime.datetime.today().strftime('%y%m%d-%H%M%S')
    return timestamp


def timestamp_str_to_datetime(timestamp: str):
    """
    Converts a timestamp string to a datetime object
    """
    my_date = datetime.datetime.strptime(timestamp, '%y%m%d-%H%M%S')
    return my_date
