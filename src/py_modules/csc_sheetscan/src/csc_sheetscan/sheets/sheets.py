# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import glob
import json
import os
import shutil
from typing import List, Sequence, Type


# ADDITIONAL MODULE IMPORTS ---------------------------------------------------
import cv2
import numpy as np
from pprint import pprint
from qreader import QReader


# LOCAL MODULE IMPORTS --------------------------------------------------------
from csc_sheetscan.utilities import (
    Log,
    sanitize_path,
    validate_uuid,
    sort_pts,
    minimum_bounding_rectangle,
    align_and_translate_mbr,
    polygon_np_xy,
    create_timestamp_str
)
from csc_sheetscan.components import SheetComponent

# ENVIRONMENT VARIABLES -------------------------------------------------------
_HERE = os.path.dirname(sanitize_path(__file__))
"""str: Directory of this particular file."""

_CONFIG_DIR = sanitize_path(os.path.join(_HERE, "config"))
"""str: Default directory to save resulting configuration files."""

_INPUTDATA_DIR = sanitize_path(os.path.join(_HERE, "inputdata"))
"""str: Default directory for input data."""

_OUTPUTDATA_DIR = sanitize_path(os.path.join(_HERE, "outputdata"))
"""str: Default directory for input data."""

_QUEUE_DIR = sanitize_path(os.path.join(_INPUTDATA_DIR, "queue"))
"""str: Default directory for input data queue."""

_DATASETS_DIR = sanitize_path(os.path.join(_INPUTDATA_DIR, "datasets"))
"""str: Default directory for compiling datasets from queue."""

_CHESSBOARD_DIR = sanitize_path(os.path.join(_QUEUE_DIR, "chess"))
"""str: Default chessboard image directory."""

_RAW_DIR = sanitize_path(os.path.join(_QUEUE_DIR, "raw"))
"""str: Default directory of raw images before undistortion."""

_UNDIST_DIR = sanitize_path(os.path.join(_OUTPUTDATA_DIR, "undist"))
"""str: Default directory to save resulting, undistorted images."""

_SHEETS_DIR = sanitize_path(os.path.join(_OUTPUTDATA_DIR, "sheets"))
"""str: Default directory to save resulting scanned sheet JSON files"""

_PROCESSED_DIR = sanitize_path(os.path.join(_OUTPUTDATA_DIR, "processed"))
"""str: Default directory for archiving processed datasets."""

_COEFF_FILE = sanitize_path(os.path.join(_CONFIG_DIR, "coefficients.yml"))
"""str: Default coefficients file."""

_XFORM_FILE = sanitize_path(os.path.join(_CONFIG_DIR, "xform.yml"))
"""str: Default xform file."""

_DEFAULTNAME = 'SCANDATA'
"""str: Default name for datasets."""


# default image for perspective transform
def __get_default_xform_img():
    """
    Get the default image for perspective transform.
    """
    folder = glob.glob(os.path.join(_UNDIST_DIR, "*.jpg"))
    try:
        return folder[0]
    except IndexError:
        return ""


_XFORM_IMG = __get_default_xform_img()
"""str: Default image for perspective transform."""


# LOGGING ---------------------------------------------------------------------

log = Log()


# FUNCTION DEFINITIONS --------------------------------------------------------

def approximate_contour(cnt, eps):
    """
    Approximate the a contour using the Ramer-Douglas-Peucker algorithm
    """
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, eps * peri, True)
    return approx


def capture_image(device: int = 0):
    """Capture an image using a connected camera and return the frame."""
    # set video device to external USB camera
    cap = cv2.VideoCapture(device, cv2.CAP_DSHOW)

    # settings for Logitech C930e
    # cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc("M", "J", "P", "G"))
    # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

    # check if the webcam is opened correctly
    if not cap.isOpened():
        raise IOError("[OPENCV] Cannot open camera!")

    # if all is fine, read one image from the camera and return it
    ret, frame = cap.read()

    # release the camera
    cap.release()
    cv2.destroyAllWindows()

    return frame


def calibrate_camera_image(image,
                           width: int = 1500,
                           height: int = 1500,
                           showresult: bool = False):

    # get corners using aruco markers
    points = detect_aruco_corners(image, showresult=showresult)
    # sort the points clockwise
    sorted_pts = sort_pts(points)
    # pixels per inch
    ppi = 96
    # millimeters per inch
    mmpi = 25.4
    # height and width in millimeters
    height = (height / mmpi) * ppi
    width = (width / mmpi) * ppi
    # define destination image based on table size
    dst_image = 255 * np.zeros(shape=[int(height), int(width), 3],
                               dtype=np.uint8)
    # extract source and destination points
    h_dst, w_dst, c_dst = dst_image.shape
    src_pts = np.float32(sorted_pts)
    dst_pts = np.float32([[0, 0], [w_dst, 0], [w_dst, h_dst], [0, h_dst]])
    # compute transformation matrix
    xform = cv2.getPerspectiveTransform(src_pts, dst_pts)
    # show the warped image to the user for debugging
    if showresult:
        warped_img = cv2.warpPerspective(image, xform, (w_dst, h_dst))
        cv2.imshow("Warped Image", warped_img)
        cv2.waitKey(0)
    # destroy all windows
    cv2.destroyAllWindows()
    # return transofmration matrix
    return xform


def calibrate_camera_file(filepath,
                          width: int = 1500,
                          height: int = 1500,
                          showresult: bool = False):
    # read image from filepath
    image = read_image(filepath)
    return calibrate_camera_image(image, width, height, showresult)


def calibrate_chessboard(images,
                         width: int = 7,
                         height: int = 9,
                         squaresize: float = 2.0,
                         displaysize: int = 1000,
                         showresult: bool = False):
    # check input
    if not images:
        log.opencv('No images found for chessboard calibration!')
        return
    # termination criteria
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    # prepare object points for the chessboard, depending on width and height
    # like (0,0,0), (1,0,0), (2,0,0) ....,(6,5,0)
    objp = np.zeros((width * height, 3), np.float32)
    objp[:, :2] = np.mgrid[0:height, 0:width].T.reshape(-1, 2)
    # multiplicate points with square size in cm
    objp = objp * squaresize
    # Arrays to store object points and image points from all the images.
    # objpoints: 3d point in real world space
    objpoints = []
    # imgpoints: 2d points in image plane.
    imgpoints = []
    # loop through test images and determine imgpoints
    log.opencv('Determining object points for camera calibration...')
    for i, fname in enumerate(images):
        log.opencv('Processing chessboard image {0} of {1}...'.format(
                                               i + 1, len(images)), end='\r')
        # read image and convert to grayscale
        img = read_image(fname)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # compute display size for image
        ih, iw = img.shape[:2]
        if ih > iw and ih > displaysize:
            rsf = displaysize / ih
        elif iw >= ih and iw > displaysize:
            rsf = displaysize / iw
        else:
            rsf = 1.0
        # find the chess board corners
        ret, corners = cv2.findChessboardCorners(gray, (height, width), None)
        # if found, add object points, image points (after refining them)
        if ret is True:
            objpoints.append(objp)
            corners2 = cv2.cornerSubPix(gray,
                                        corners,
                                        (11, 11),
                                        (-1, -1),
                                        criteria)
            imgpoints.append(corners2)
            # show results for debugging
            if showresult:
                # draw and display the corners
                cv2.drawChessboardCorners(img, (height, width), corners2, ret)
                windowname = "Found object points in image"
                cv2.namedWindow(windowname, flags=cv2.WINDOW_NORMAL)
                cv2.resizeWindow(windowname, int(iw * rsf), int(ih * rsf))
                cv2.imshow(windowname, img)
                cv2.waitKey(500)
        else:
            log.opencv('Chessboard corners could not be found for '
                       'image {0}'.format(fname))
    # close all windows
    cv2.destroyAllWindows()
    # calibrate camera by computing camera matrix, distortion coefficients,
    # rotation and translation vectors
    ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints,
                                                       imgpoints,
                                                       gray.shape[::-1],
                                                       None, None)
    # return camera calibration values
    return ret, mtx, dist, rvecs, tvecs


def compute_camera_coefficients(chessboard_dir: str = _CHESSBOARD_DIR,
                                coeff_file: str = _COEFF_FILE,
                                verbose: bool = False,
                                showresult: bool = False):
    """
    Computes the camera coefficients and saves them to a file.
    """
    # sanitize input filepath
    if not coeff_file:
        raise ValueError(("Supplied coeff_file {0} is not a valid file "
                          "for storing the coefficients!").format(coeff_file))
    else:
        log.opencv(f'Using ...{coeff_file[-50:]} for storage of coefficients.')
    # define data directories
    if not os.path.isdir(chessboard_dir):
        raise ValueError((f'Supplied chessboard_dir {chessboard_dir} is not '
                          'a valid directory!'))
    else:
        log.opencv(f'Using ...{chessboard_dir[-50:]} as directory for '
                   'chessboard images.')
    # find calibration images
    chessboard_imgs = glob.glob(os.path.join(chessboard_dir, '*.jpg'))
    # calibrate
    ret, mtx, dist, rvecs, tvecs = calibrate_chessboard(
                                            chessboard_imgs,
                                            showresult=showresult)
    if verbose:
        # print results
        print("[OPENCV] Camera matrix:")
        print(mtx, "\n")
        print("[OPENCV] Distortion:")
        print(dist, "\n")
        print("[OPENCV] Rotation:")
        print(rvecs, "\n")
        print("[OPENCV] Translation:")
        print(tvecs, "\n")
    # save the coefficients
    save_coefficients(mtx, dist, coeff_file)
    # print info
    log.opencv('Camera coefficients successfully saved to file:')
    log.opencv(coeff_file)
    # return the coefficients
    return (mtx, dist)


def compute_perspective_xform(img_file: str = _XFORM_IMG,
                              xform_file: str = _XFORM_FILE,
                              width: int = 1500,
                              height: int = 1500,
                              showresult: bool = False):
    """
    Computes the transformation matrix for perspective transform and saves
    the results to a file.
    """
    # sanitize image filepath
    if not img_file or not os.path.isfile(img_file):
        log.info(img_file)
        raise ValueError(f'Supplied image {img_file} is not a valid image '
                         'file!')
    else:
        log.opencv(f'Using ...{img_file[-50:]} as image for computing '
                   'perspective transform.')
    # sanitize xform filepath
    if not xform_file:
        raise ValueError(f'Supplied {xform_file} is not a valid file for '
                         'storing the perspective transformation!')
    else:
        log.opencv(f'Using ...{xform_file[-50:]} for storage of perspective '
                   'transform.')
    # compute xform matrix
    xform = calibrate_camera_file(img_file,
                                  width,
                                  height,
                                  showresult)
    # save xform to file
    save_perspective_xform(xform, xform_file)
    # print info
    log.opencv('Perspective transformation matrix successfully '
               'saved to file:')
    log.opencv(xform_file)
    # return xform data
    return xform


def detect_aruco_corners(image,
                         showresult: bool = False):
    # copy image to be safe
    aruco_img = image.copy()
    # get aruco dict and create detector instance
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    aruco_det = cv2.aruco.ArucoDetector(aruco_dict)
    # detect aruco markers
    (corners, ids, rejected) = aruco_det.detectMarkers(aruco_img)
    # check integrity
    if len(corners) != 4:
        pprint(corners)
        pprint(ids)
        pprint(rejected)
        raise RuntimeError('[ERROR] There has to be exactly four markers!')
    else:
        log.opencv('Found 4 ARUCO Markers. Processing...')
    # loop over corner data and create marker tuples
    # id, corner_pts_list, centerpt, marker_corners, cv_corners
    aruco_markers = []
    for i, marker_corners in enumerate(corners):
        marker_id = int(ids[i].tolist()[0])
        corner_pts_list = marker_corners.astype(int).tolist()[0]
        x_sum = (marker_corners[0][0][0] + marker_corners[0][2][0]) / 2
        y_sum = (marker_corners[0][0][1] + marker_corners[0][2][1]) / 2
        centerpt = [int(x_sum), int(y_sum)]
        cv_corners = marker_corners.astype(np.int32).reshape((-1, 1, 2))
        aruco_markers.append((marker_id,
                              corner_pts_list,
                              centerpt,
                              marker_corners,
                              cv_corners))
    # sort markers by their id
    aruco_markers.sort()
    # get inner corners
    # assume that 0 marker is always top left and order is CW (for now...)!
    log.warn('Will assume that 0 is top left and order is CW!')
    inner_corners = [(aruco_markers[0][1][1][0], aruco_markers[0][1][1][1]),
                     (aruco_markers[1][1][2][0], aruco_markers[1][1][2][1]),
                     (aruco_markers[2][1][3][0], aruco_markers[2][1][3][1]),
                     (aruco_markers[3][1][0][0], aruco_markers[3][1][0][1]),]
    # display results if flag is set
    if showresult:
        display_img = aruco_img.copy()
        for i, marker in enumerate(aruco_markers):
            cv_corners = marker[4]
            cv2.circle(display_img, inner_corners[i], 4, (0, 0, 255), -1)
            cv2.polylines(display_img, [cv_corners], True, (0, 255, 255))
            cv2.putText(display_img,
                        str(marker[0]),
                        (marker[2][0], marker[2][1]),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        2.5,
                        (0, 0, 255),
                        4)
        windowname = 'ARUCO Detected Image'
        cv2.namedWindow(windowname, flags=cv2.WINDOW_NORMAL)
        cv2.imshow(windowname, display_img)
        cv2.waitKey(20000)
        cv2.destroyAllWindows()
    # return inner corners
    return inner_corners


def detect_contours_from_file(filepath: str,
                              thresh_binary: int,
                              thresh_area: float,
                              approx: int = 0,
                              invert: bool = False,
                              extonly: bool = False,
                              otsu: bool = False,
                              largestonly: bool = True):
    """
    Detect Contours in an image file.
    """
    image = read_image(filepath)
    return detect_contours_from_image(image,
                                      thresh_binary,
                                      thresh_area,
                                      approx,
                                      invert,
                                      extonly,
                                      otsu,
                                      largestonly)


def detect_contours_from_image(image: np.ndarray,
                               thresh_binary: int,
                               thresh_area: float,
                               approx: int = 0,
                               invert: bool = False,
                               extonly: bool = False,
                               otsu: bool = True,
                               largestonly: bool = True):
    """
    Detect Contors in an image.
    """
    if invert:
        if otsu:
            threshold_type = cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            thresh_binary = 0
        else:
            threshold_type = cv2.THRESH_BINARY_INV
    else:
        if otsu:
            threshold_type = cv2.THRESH_BINARY + cv2.THRESH_OTSU
            thresh_binary = 0
        else:
            threshold_type = cv2.THRESH_BINARY
    # flip image to avoid mirrored contours
    image = cv2.flip(image, 0)
    # convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # create a binary thresholded image
    _, binary = cv2.threshold(gray, thresh_binary, 255, threshold_type)
    # determine chain approximation
    chain_approx = cv2.CHAIN_APPROX_NONE
    if approx <= 0:
        chain_approx = cv2.CHAIN_APPROX_NONE
    elif approx == 1:
        chain_approx = cv2.CHAIN_APPROX_SIMPLE
    elif approx == 2:
        chain_approx = cv2.CHAIN_APPROX_TC89_L1
    else:
        chain_approx = cv2.CHAIN_APPROX_TC89_KCOS
    # find the contours from the thresholded image
    # CHAIN_APPROX_NONE
    # CHAIN_APPROX_SIMPLE
    # CHAIN_APPROX_TC89_L1
    # CHAIN_APPROX_TC89_KCOS
    contours, hierarchy = cv2.findContours(binary,
                                           cv2.RETR_TREE,
                                           chain_approx)
    # sort contours by area and filter against threshold
    # only return outermost contours, no inner contours based on hierarchy
    if abs(thresh_area) > 0:
        areas = [cv2.contourArea(cnt) for cnt in contours]
        if extonly:
            contours = [contours[i] for i in range(len(contours))
                        if areas[i] > abs(thresh_area) and
                        hierarchy[0][i][3] == -1]
        else:
            contours = [contours[i] for i in range(len(contours))
                        if areas[i] > abs(thresh_area)]
    else:
        if extonly:
            contours = [contours[i] for i in range(len(contours))
                        if hierarchy[0][i][3] == -1]

    if largestonly:
        contours = [max(contours, key=cv2.contourArea)]
    # colour detection and mean averaging inside contours
    colors = []
    for i, cnt in enumerate(contours):
        # create a mask for the current contour
        mask = np.zeros(gray.shape, np.uint8)
        cv2.drawContours(mask, [cnt], 0, 255, -1)
        mean_val = cv2.mean(image, mask=mask)
        # append color as RGB (convert from BGRA)
        colors.append((int(round(mean_val[2])),
                       int(round(mean_val[1])),
                       int(round(mean_val[0]))))
    return image, contours, colors


def detect_qr_codes_from_file(filepath: str,
                              crop: int = 1500,
                              showcrop: bool = False,
                              showresult: bool = False):
    """
    Detect QR-Codes in an image file.
    """
    return detect_qr_codes_from_image(read_image(filepath),
                                      crop=crop,
                                      showcrop=showcrop,
                                      showresult=showresult)


def detect_qr_codes_from_image(image: np.ndarray,
                               crop: int = 1500,
                               showcrop: bool = False,
                               showresult: bool = False):
    """
    Detect QR-Codes in an image.
    """
    # copy the image for security reasons
    img = image.copy()
    # crop image to increase chances of qr detection
    if crop > 0:
        center = img.shape
        x = center[1] / 2 - crop / 2
        y = center[0] / 2 - crop / 2
        crop_img = img[int(y):int(y + crop), int(x):int(x + crop)]
    else:
        crop_img = img
    # display cropped image for debug (optional)
    if showcrop:
        windowname = 'Cropped Image'
        cv2.namedWindow(windowname, flags=cv2.WINDOW_NORMAL)
        cv2.imshow(windowname, crop_img)
        cv2.waitKey(20000)
        cv2.destroyAllWindows()
    # Create a QReader instance using large model
    qreader = QReader(model_size='s', min_confidence=0.5)
    # Detect and decode QR Codes, only using the first one
    det_code = qreader.detect_and_decode(crop_img,
                                         return_detections=True,
                                         is_bgr=True)
    # Disassemble detected and decoded data
    code_uuid = str(det_code[0][0])
    log.qreader(f'Found QRCODE: {code_uuid}')
    if validate_uuid(code_uuid):
        log.info(f'UUID {code_uuid} is valid.')
    else:
        log.warn(f'UUID {code_uuid} is NOT valid!!!')
        raise RuntimeError(f'UUID {code_uuid} is not a valid uuid!')
    # Display results if flag is set
    if showresult:
        code_bbx = det_code[1][0]['bbox_xyxy']
        x1 = int(code_bbx[0])
        y1 = int(code_bbx[1])
        x2 = int(code_bbx[2])
        y2 = int(code_bbx[3])
        cv2.rectangle(crop_img, (x1, y1), (x2, y2), (0, 0, 255), 2)
        text = f'{code_uuid}'
        cv2.putText(crop_img,
                    text,
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.2,
                    (0, 0, 255),
                    2)
        windowname = 'Processed Image'
        cv2.namedWindow(windowname, flags=cv2.WINDOW_NORMAL)
        cv2.imshow(windowname, crop_img)
        cv2.waitKey(20000)
        cv2.destroyAllWindows()
    # return code id
    return code_uuid


def read_image(filepath: str):
    """Wrapper for cv2.imread"""
    return cv2.imread(os.path.normpath(filepath))


def undistort_image(image, mtx, dist, remap: bool = True):
    # get height and width of input image
    h, w = image.shape[:2]
    # compute new camera matrix based on calibrated matrix and distortion
    newcameramtx, roi = cv2.getOptimalNewCameraMatrix(mtx,
                                                      dist,
                                                      (w, h),
                                                      1,
                                                      (w, h))
    # undistort using remap function
    if remap:
        mapx, mapy = cv2.initUndistortRectifyMap(mtx,
                                                 dist,
                                                 None,
                                                 newcameramtx,
                                                 (w, h),
                                                 5)
        undistorted_image = cv2.remap(image, mapx, mapy, cv2.INTER_LINEAR)

    # undistort using undistort function
    else:
        undistorted_image = cv2.undistort(image, mtx, dist, None, newcameramtx)

    # crop the image
    x, y, w, h = roi
    undistorted_image = undistorted_image[y:y+h, x:x+w]

    # return resulting undistorted image
    return undistorted_image


def undistort_image_files(indir: str = _RAW_DIR,
                          outdir: str = _UNDIST_DIR,
                          coeff_file: str = _COEFF_FILE):

    # sanitize input filepaths
    if not os.path.isfile(coeff_file):
        raise ValueError(f'Supplied coeff_file {coeff_file} is not a valid '
                         'file for storing the coefficients!')
    else:
        log.opencv(f'Using ...{coeff_file[-50:]} for loading of coefficients.')

    if not os.path.isdir(indir):
        raise ValueError(f'Supplied indir {indir} is not a valid directory!')
    else:
        log.opencv(f'Using ...{indir[-50:]} as input directory.')

    if not os.path.isdir(outdir):
        raise ValueError(f'Supplied outdir {outdir} is not a valid '
                         'directory!')
    else:
        log.opencv(f'Using ...{outdir[-50:]} as output directory.')

    # load coefficients from previously saved file
    log.opencv('Loading camera coefficients from file...')
    mtx, dist = load_coefficients(sanitize_path(coeff_file))

    # apply the camera matrix to all target images
    log.opencv('Applying undistortion to all raw images...')

    # get all scan images to apply undistortion to...
    scan_imgs = glob.glob(os.path.join(indir, '*.jpg'))

    for i, img in enumerate(scan_imgs):
        log.opencv('Undistorting image {0} of {1}'.format(
                i + 1, len(scan_imgs)), end='\r')
        # apply undistortion
        undistorted_img = undistort_image(read_image(img),
                                          mtx,
                                          dist)

        # write undistorted image to new file
        cv2.imwrite(sanitize_path(os.path.join(outdir,
                                  os.path.split(img)[1])), undistorted_img)
    log.opencv('Successfully undistorted {0} images!'.format(len(scan_imgs)))


def preprocess_image_file(fp: str, border: int = 80):
    """
    Preprocess an image file to get rid of arcuo detection bugs. Add white
    border around image and save it.
    """
    image = read_image(fp)
    border_type = cv2.BORDER_CONSTANT
    white = [255, 255, 255]
    result = cv2.copyMakeBorder(image,
                                border,
                                border,
                                border,
                                border,
                                border_type,
                                None,
                                white)
    cv2.imwrite(fp, result)


def preprocess_image_files(indir: str, border: int = 80):
    """
    Preprocess a whole image folder to get rid of arcuo detection bugs. Add
    white border around image and save it.
    """
    if not os.path.isdir(indir):
        raise ValueError(f'Supplied indir {indir} is not a valid directory!')
    else:
        log.opencv(f'Using ...{indir[-50:]} as input directory.')

    # get all scan images to apply undistortion to...
    imgs = glob.glob(os.path.join(indir, "*.jpg"))

    for i, img in enumerate(imgs):
        log.opencv("Preprocessing image {0} of {1}".format(
                i + 1, len(imgs)), end='\r')
        # apply preprocessing
        preprocess_image_file(img)

    log.opencv(f'Successfully preprocessed {len(imgs)} images!')


def detect_contours_and_ids(dirpath: str = _UNDIST_DIR,
                            xformfile: str = _XFORM_FILE,
                            bthresh: int = -1,
                            athresh: float = 20000.0,
                            width: int = 1500,
                            height: int = 1500,
                            thickness: float = 12.0,
                            chain: int = 0,
                            eps: float = 0.001,
                            invert: bool = False,
                            external: bool = True,
                            largestonly: bool = True,
                            qrcrop: int = 1500,
                            showcrop: bool = False,
                            showresult: bool = False) -> List[SheetComponent]:
    """
    Detect contours and QR Codes in images.
    """
    # read all images from the directory filepath
    img_types = ['*.jpg', '*.png', '*.jpeg']
    img_files = []
    for imt in img_types:
        img_files.extend(glob.glob(os.path.join(dirpath, imt)))
    # retrieve transformation matrix from xform file
    xform = load_perspective_xform(xformfile)
    # set otsu flag
    if bthresh == -1:
        otsu = True
    else:
        otsu = False
    # loop over all image file paths in the directory
    sheets = []
    for i, fp in enumerate(img_files):
        log.info('Processing input image '
                 f'{os.path.basename(fp)} ({i + 1}/{len(img_files)})...')
        # read image into numpy array
        image = read_image(fp)
        # create warped image using xform
        warped_img = warp_image(image, xform, width, height)
        # copy image and perform qr code detection
        log.qreader('Running QR Code detection...')
        sheet_id = detect_qr_codes_from_image(
                                        warped_img,
                                        crop=qrcrop,
                                        showcrop=showcrop,
                                        showresult=showresult)
        # run contour detection using opencv
        log.opencv('Running Contour detection...')
        warped_img, contours, colors = detect_contours_from_image(
                                                            warped_img,
                                                            bthresh,
                                                            athresh,
                                                            chain,
                                                            invert,
                                                            external,
                                                            otsu,
                                                            largestonly)
        # compute scaling factor for results
        h_dst, w_dst, c_dst = warped_img.shape
        scalingfactor = width / w_dst
        # construct polylines from contour output
        log.info('Aligning contour polylines and computing MBR...')
        sheet_polygons = []
        sheet_mbrs = []
        # process contour curves
        for cnt in contours:
            if len(cnt) >= 2:
                if eps > 0.0:
                    cntpts = approximate_contour(cnt, eps)
                else:
                    cntpts = cnt
                # scale contours using computed scaling factor
                cntpts = cntpts * scalingfactor
                # convert to np array of polygon points
                polygon_pts = polygon_np_xy(cntpts)
                # find mbr and align
                mbr, angle = minimum_bounding_rectangle(polygon_pts)
                aligned_polygon, aligned_mbr = align_and_translate_mbr(
                    polygon_pts,
                    mbr,
                    angle)
                # append to output list
                sheet_polygons.append(aligned_polygon.tolist())
                sheet_mbrs.append(aligned_mbr.tolist())
        # create sheet component using the data
        sheet_obj = SheetComponent(
            _id=sheet_id,
            material='corian',
            profile=sheet_polygons[0],
            complexity=1,
            fragment=True,
            color=colors[0],
            bbx=sheet_mbrs[0],
            location=[0, 0],
            descriptors={},
            processes={},
            validated=True
        )
        sheets.append(sheet_obj)
    # return sheet objects
    return sheets


def load_input_dataset(fp: str):
    """
    Loads an input scanning dataset and returns the relevant filepaths.
    """
    dataset_name = os.path.split(fp)[1]
    # create folder names
    chessdir = '_'.join([dataset_name, 'chess'])
    rawdir = '_'.join([dataset_name, 'raw'])
    undist = '_'.join([dataset_name, 'undist'])

    # create directory paths
    main_path = sanitize_path(os.path.join(_DATASETS_DIR, dataset_name))
    chess_path = sanitize_path(os.path.join(main_path, chessdir))
    raw_path = sanitize_path(os.path.join(main_path, rawdir))
    undist_path = sanitize_path(os.path.join(main_path, undist))

    # create coeff file paths
    coeff_filename = '_'.join([dataset_name, 'coefficients.yml'])
    coeff_file = sanitize_path(os.path.join(main_path, coeff_filename))

    # create xform file paths
    xform_filename = '_'.join([dataset_name, 'xform.yml'])
    xform_file = sanitize_path(os.path.join(main_path, xform_filename))

    # find all queue files
    # find chessboard imgages
    chess_imgs = glob.glob(os.path.join(chess_path, '*.jpg'))
    if not chess_imgs:
        raise RuntimeError('[ERROR] No Chessboard images found!')

    # find raw images
    raw_imgs = glob.glob(os.path.join(raw_path, '*.jpg'))
    if not raw_imgs:
        raise RuntimeError('[ERROR] No Raw images found!')

    # find undist images
    undist_imgs = glob.glob(os.path.join(undist_path, '*.jpg'))
    if not undist_imgs:
        raise RuntimeError('[ERROR] No Undistorted images found!')

    # return a tuple of all relevant data locations
    return (main_path,
            chess_path,
            raw_path,
            undist_path,
            coeff_file,
            xform_file,
            chess_imgs,
            raw_imgs,
            undist_imgs)


def get_all_input_datasets(fp: str = _DATASETS_DIR):
    """
    Use globbing to get all input dataset directory paths.
    """
    datasets = [sanitize_path(f.path) for f in os.scandir(fp) if f.is_dir()]
    return datasets


def save_sheet_to_json(sheet: dict,
                       dirpath: str = _SHEETS_DIR):
    """
    Takes a scanned sheet as dictionary and writes it to as JSON file.
    """
    # create json object
    sheet_obj = json.dumps(sheet, indent=4)
    # write json object to dedicated file
    filepath = sanitize_path(os.path.join(dirpath, sheet['_id'] + '.json'))
    with open(filepath, 'w') as jsonfile:
        jsonfile.write(sheet_obj)
    log.info(f'Sheet {sheet["_id"]} successfully saved to JSON file!')
    return True


def save_sheets_to_json(sheets: Sequence[Type[SheetComponent]],
                        dirpath: str = _SHEETS_DIR):
    """
    Saves a list of sheet dictionaries to JSON files.
    """
    for sheet in sheets:
        sheet.save_to_json(dirpath)
        log.info(f'Sheet {sheet.id} successfully saved to JSON file!')
    return True


def load_sheet_from_json(fp: str):
    """
    Load .JSON file containing a sheet description and return sheet dict.
    """
    json_object = None
    with open(fp, 'r') as sheet:
        # Reading from json file
        json_object = json.load(sheet)
    # return JSON dict
    return json_object


def warp_image(image, xform, width, height):
    """
    Wrapper for cv2.warpPerspective.
    """
    # pixels per inch
    ppi = 96
    # millimeters per inch
    mmpi = 25.4
    # height and width in millimeters
    height = int((height / mmpi) * ppi)
    width = int((width / mmpi) * ppi)
    # return warped result
    return cv2.warpPerspective(image, xform, (width, height))


def prepare_dataset(queuedir: str = _QUEUE_DIR,
                    datasetsdir: str = _DATASETS_DIR,
                    name: str = _DEFAULTNAME):
    """
    Read from the queue and prepare a dataset.
    Returns a tuple of all relevant file and directory paths.
    """
    # create timestamp
    timestamp = create_timestamp_str()
    # create folder names
    fullname = '_'.join([timestamp, name])
    chessdir = '_'.join([timestamp, name, 'chess'])
    rawdir = '_'.join([timestamp, name, 'raw'])
    undist = '_'.join([timestamp, name, 'undist'])
    # create directory paths
    main_path = sanitize_path(os.path.join(_DATASETS_DIR, fullname))
    chess_path = sanitize_path(os.path.join(main_path, chessdir))
    raw_path = sanitize_path(os.path.join(main_path, rawdir))
    undist_path = sanitize_path(os.path.join(main_path, undist))

    # create coeff file paths
    coeff_filename = '_'.join([fullname, 'coefficients.yml'])
    coeff_file = sanitize_path(os.path.join(main_path, coeff_filename))

    # create xform file paths
    xform_filename = '_'.join([fullname, 'xform.yml'])
    xform_file = sanitize_path(os.path.join(main_path, xform_filename))

    # make dirs
    os.makedirs(main_path)
    os.makedirs(chess_path)
    os.makedirs(raw_path)
    os.makedirs(undist_path)

    # find all queue files
    # find chessboard imgages
    chess_inpath = sanitize_path(os.path.join(_QUEUE_DIR, 'chess'))
    chess_imgs = glob.glob(os.path.join(chess_inpath, '*.jpg'))
    if not chess_imgs:
        raise RuntimeError('[ERROR] No Chessboard images found!')

    # find raw images
    raw_inpath = sanitize_path(os.path.join(_QUEUE_DIR, 'raw'))
    raw_imgs = glob.glob(os.path.join(raw_inpath, '*.jpg'))
    if not raw_imgs:
        raise RuntimeError('[ERROR] No Raw images found!')

    # copy chessboard images
    for img in chess_imgs:
        shutil.copy2(img, chess_path)

    # copy raw images
    for img in raw_imgs:
        shutil.copy2(img, raw_path)

    # return a tuple of all relevant data locations
    return (main_path,
            chess_path,
            raw_path,
            undist_path,
            coeff_file,
            xform_file)


def save_dataset_to_archive(rootdir: str,
                            outdir: str = _PROCESSED_DIR):
    """
    Saves the dataset as a zip archive.
    """
    archive_name = os.path.join(outdir, os.path.basename(rootdir))
    log.info(f'Archiving dataset to {archive_name}')
    shutil.make_archive(archive_name, 'zip', rootdir)


# UTILITY FUNCTIONS -----------------------------------------------------------

def load_coefficients(path: str):
    """
    Loads camera matrix and distortion coefficients.
    """
    cv_file = cv2.FileStorage(path, cv2.FILE_STORAGE_READ)
    camera_matrix = cv_file.getNode('K').mat()
    dist_matrix = cv_file.getNode('D').mat()
    cv_file.release()
    return (camera_matrix, dist_matrix)


def load_perspective_xform(path: str):
    """
    Loads camera calibration transformation matrix.
    """
    cv_file = cv2.FileStorage(path, cv2.FILE_STORAGE_READ)
    xform = cv_file.getNode("XFORM").mat()
    cv_file.release()
    return xform


def save_coefficients(mtx, dist, path):
    """
    Save the camera matrix and the distortion coefficients to given path/file.
    """
    cv_file = cv2.FileStorage(path, cv2.FILE_STORAGE_WRITE)
    cv_file.write('K', mtx)
    cv_file.write('D', dist)
    cv_file.release()


def save_perspective_xform(xform, path):
    """
    Save the camera calibration transformation matrix to given path/file.
    """
    cv_file = cv2.FileStorage(path, cv2.FILE_STORAGE_WRITE)
    cv_file.write('XFORM', xform)
    cv_file.release()


def find_xform_img(indir: str):
    """
    Return first image in given folder to use as xform image during
    perspective transform computation.
    """
    folder = glob.glob(os.path.join(indir, '*.jpg'))
    try:
        return folder[0]
    except IndexError:
        return ""


# TEST MODULE -----------------------------------------------------------------

def test_detect_contours_from_file():
    # use the demo image to perform some contour detection
    thisfolder = os.path.dirname(sanitize_path((__file__)))
    fp = sanitize_path(os.path.join(thisfolder, 'resources', 'demo_image.jpg'))
    image, crvs = detect_contours_from_file(fp, 170, 50.0)

    # draw only largest contour
    image = cv2.drawContours(image, crvs, -1, (0, 255, 0), 2)

    # show the image
    cv2.imshow('image', image)

    cv2.waitKey(10000)
    cv2.destroyAllWindows()


def test_detect_contours_from_image():
    # capture an image to perform some contour detection
    image, crvs, colors = detect_contours_from_image(
                                    capture_image(), 170, 50.0, False)

    # draw only largest contour
    image = cv2.drawContours(image, crvs, -1, (0, 255, 0), 2)

    # show the image
    cv2.imshow('Detected Contours in Captured Image', image)

    cv2.waitKey(10000)
    cv2.destroyAllWindows()


def test_detect_qr_codes_from_file():
    thisfolder = os.path.dirname(sanitize_path((__file__)))
    fp = sanitize_path(os.path.join(thisfolder, 'resources',
                                    'qr_detection_test.jpg'))
    detect_qr_codes_from_file(fp, showresult=True)


def test_aruco_detection(showresult: bool = False):
    # path to folder
    thisfolder = os.path.dirname(sanitize_path((__file__)))

    # read image to detect aruco markers
    aruco_img = read_image(os.path.join(thisfolder, 'resources',
                                        'aruco_test.jpg'))
    # get aruco dict and create detector instance
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    aruco_det = cv2.aruco.ArucoDetector(aruco_dict)

    # detect aruco markers
    (corners, ids, rejected) = aruco_det.detectMarkers(aruco_img)
    # check integrity
    if len(corners) != 4:
        raise RuntimeError('[ERROR] There has to be exactly four markers!')

    # loop over corner data and create marker tuples
    # id, corner_pts_list, centerpt, marker_corners, cv_corners
    aruco_markers = []
    for i, marker_corners in enumerate(corners):
        marker_id = int(ids[i].tolist()[0])
        corner_pts_list = marker_corners.astype(int).tolist()[0]
        x_sum = (marker_corners[0][0][0] + marker_corners[0][2][0]) / 2
        y_sum = (marker_corners[0][0][1] + marker_corners[0][2][1]) / 2
        centerpt = [int(x_sum), int(y_sum)]

        cv_corners = marker_corners.astype(np.int32).reshape((-1, 1, 2))

        aruco_markers.append((marker_id,
                              corner_pts_list,
                              centerpt,
                              marker_corners,
                              cv_corners))
    aruco_markers.sort()

    inner_corners = [(aruco_markers[0][1][1][0], aruco_markers[0][1][1][1]),
                     (aruco_markers[1][1][2][0], aruco_markers[1][1][2][1]),
                     (aruco_markers[2][1][3][0], aruco_markers[2][1][3][1]),
                     (aruco_markers[3][1][0][0], aruco_markers[3][1][0][1]),]

    log.info('Detected ARUCO Data:')
    [print(marker) for marker in aruco_markers]

    # display results if flag is set
    if showresult:
        display_img = aruco_img.copy()
        for i, marker in enumerate(aruco_markers):
            cv_corners = marker[4]
            cv2.circle(display_img, inner_corners[i], 4, (0, 0, 255), -1)
            cv2.polylines(display_img, [cv_corners], True, (0, 255, 255))
            cv2.putText(display_img,
                        str(marker[0]),
                        (marker[2][0], marker[2][1]),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        2.5,
                        (0, 0, 255),
                        4)
        windowname = 'ARUCO Detected Image'
        cv2.namedWindow(windowname, flags=cv2.WINDOW_NORMAL)
        cv2.imshow(windowname, display_img)
        cv2.waitKey(20000)
        cv2.destroyAllWindows()


def test_preprocessing():
    thisfolder = os.path.dirname(sanitize_path((__file__)))
    preprocessing_test = os.path.join(thisfolder,
                                      'resources',
                                      'preprocess_test.jpg')
    preprocess_image_file(preprocessing_test)


# MAIN ROUTINE ----------------------------------------------------------------

if __name__ == "__main__":
    pass
    # # Test contour detection
    # test_detect_contours_from_file()

    # # Test QR-Code detection
    # test_detect_qr_codes_from_file()

    # scan_sheets()

    # test_preprocessing()

    # prepare_dataset()

    # for ds in get_all_input_datasets():
    #     print(load_input_dataset(ds))
