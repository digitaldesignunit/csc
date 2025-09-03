# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import argparse
import os
import uuid
import glob
from typing import Optional
import time

# ADDITIONAL MODULE IMPORTS ---------------------------------------------------
import cv2
import numpy as np
from qreader import QReader


# PROFILER UTILITY ------------------------------------------------------------

class Profiler(object):
    """
    A very simple profiler
    """

    def __init__(self):
        self.start_time = None
        self.stop_time = None

    def start(self):
        """
        Start the timer and save the start time.
        """
        self.stop_time = None
        self.start_time = time.time()

    def stop(self):
        """
        Stop the timer, print and return elapsed time.
        """
        elapsed = time.time() - self.start_time
        self.stop_time = elapsed
        elapsed_ms = elapsed * 1000
        print('Elapsed Time:')
        print(str(round(elapsed, 3)) + ' s')
        print(str(round(elapsed_ms, 3)) + ' ms')
        return elapsed_ms

    def rawstop(self):
        """
        Stop the timer raw and don't print the results
        """
        elapsed = time.time() - self.start_time
        self.stop_time = elapsed
        elapsed_ms = elapsed * 1000
        return elapsed_ms

    def results(self):
        """
        Print the latest timing results
        """
        if self.stop_time is None:
            print('Timer is still running! Call stop() method first.')
            return None
        print('Elapsed Time:')
        print(str(round(self.stop_time, 3)) + ' s')
        print(str(round(self.stop_time * 1000, 3)) + ' ms')
        return self.stop_time * 1000


# FUNCTION DEFINITIONS --------------------------------------------------------

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


def read_image(filepath: str):
    """Wrapper for cv2.imread"""
    return cv2.imread(os.path.normpath(filepath))


def detect_qr_codes_from_file(filepath: str,
                              showresult: bool = False,
                              crop_ratio: float = 1.0):
    """
    Detect QR-Codes in an image file.
    """
    return detect_qr_codes_from_image(read_image(filepath),
                                      showresult=showresult,
                                      crop_ratio=crop_ratio)


def detect_qr_codes_from_image(image: np.ndarray,
                               showresult: bool = False,
                               crop_ratio: float = 1.0) -> Optional[str]:
    """
    Detect QR-Codes in an image.

    Parameters
    ----------
    image : np.ndarray
        Input image
    showresult : bool, default=False
        Show result with bounding box
    crop_ratio : float, default=1.0
        Pre-crop ratio for single pass (0.0-1.0, based on smaller dimension)

    Returns
    -------
    str or None
        The decoded QR code UUID if found and valid, None otherwise.
    """
    # copy the image for security reasons
    img = image.copy()
    return _detect_qr_single_pass(img, showresult, crop_ratio)


def _detect_qr_single_pass(img: np.ndarray, showresult: bool,
                           crop_ratio: float = 1.0) -> Optional[str]:
    """Detect QR code in a single pass over the full image."""
    # Apply pre-crop if specified
    if crop_ratio < 1.0:
        height, width = img.shape[:2]
        min_dim = min(width, height)
        crop_size = int(min_dim * crop_ratio)

        # Calculate center crop coordinates
        center_x = width // 2
        center_y = height // 2
        half_crop = crop_size // 2

        x1 = max(0, center_x - half_crop)
        y1 = max(0, center_y - half_crop)
        x2 = min(width, center_x + half_crop)
        y2 = min(height, center_y + half_crop)

        img = img[y1:y2, x1:x2]
        print(f'Pre-cropped image to {crop_size}x{crop_size} centered square')

    # Create a QReader instance using large model
    qreader = QReader(model_size='s', min_confidence=0.5)
    # Detect and decode QR Codes, only using the first one
    det_code = qreader.detect_and_decode(img,
                                         return_detections=True,
                                         is_bgr=True)

    # Check if any QR codes were detected
    if not det_code[0] or len(det_code[0]) == 0:
        return None

    # Disassemble detected and decoded data
    code_uuid = str(det_code[0][0])
    print(f'Found QRCODE: {code_uuid}')
    if validate_uuid(code_uuid):
        print(f'UUID {code_uuid} is valid.')
        # Display results if flag is set
        if showresult:
            code_bbx = det_code[1][0]['bbox_xyxy']
            x1 = int(code_bbx[0])
            y1 = int(code_bbx[1])
            x2 = int(code_bbx[2])
            y2 = int(code_bbx[3])
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
            text = f'{code_uuid}'
            cv2.putText(img,
                        text,
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.2,
                        (0, 0, 255),
                        2)
            windowname = 'Processed Image'
            cv2.namedWindow(windowname, flags=cv2.WINDOW_NORMAL)
            cv2.imshow(windowname, img)
            cv2.waitKey(20000)
            cv2.destroyAllWindows()
        return code_uuid
    else:
        print(f'UUID {code_uuid} is NOT valid!!!')
        return None


def get_image_files(folder_path: str) -> list[str]:
    """
    Get all image files from a folder.

    Parameters
    ----------
    folder_path : str
        Path to the folder containing images

    Returns
    -------
    list[str]
        List of image file paths
    """
    image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.tiff', '*.tif']
    image_files = set()  # Use set to avoid duplicates

    for extension in image_extensions:
        pattern = os.path.join(folder_path, extension)
        image_files.update(glob.glob(pattern))
        # Also check uppercase extensions
        pattern_upper = os.path.join(folder_path, extension.upper())
        image_files.update(glob.glob(pattern_upper))

    return sorted(list(image_files))


def detect_qr_code_in_photo_set(folder_path: str,
                                skip_interval: int = 1,
                                showresult: bool = False,
                                crop_ratio: float = 1.0) -> Optional[str]:
    """
    Detect QR code in a set of photos from a folder.

    Parameters
    ----------
    folder_path : str
        Path to the folder containing photos
    skip_interval : int, default=1
        Check every nth photo (1 = check all, 3 = check every 3rd photo, etc.)
    showresult : bool, default=False
        Show result with bounding box
    crop_ratio : float, default=1.0
        Pre-crop ratio for single pass (0.0-1.0, based on smaller dimension)

    Returns
    -------
    str or None
        The decoded QR code UUID if found and valid, None if not found
    """
    print(f'Scanning folder: {folder_path}')
    print(f'Skip interval: {skip_interval} '
          f'(checking every {skip_interval} photo)')

    # Get all image files
    image_files = get_image_files(folder_path)

    if not image_files:
        print('No image files found in the specified folder.')
        return None

    print(f'Found {len(image_files)} image files')

    # Process images with skip interval
    for i, image_path in enumerate(image_files):
        if (i + 1) % skip_interval != 0:
            continue

        print(f'Processing image {i+1}/{len(image_files)}: '
              f'{os.path.basename(image_path)}')

        try:
            # Try to detect QR code in this image
            qr_code = detect_qr_codes_from_file(
                image_path,
                showresult=showresult,
                crop_ratio=crop_ratio
            )

            if qr_code:
                print(f'Successfully found and validated QR code: {qr_code}')
                print(f'Found in image: {os.path.basename(image_path)}')
                return qr_code
            else:
                print(f'No valid QR code found in '
                      f'{os.path.basename(image_path)}')

        except Exception as e:
            print(f'Error processing {os.path.basename(image_path)}: {str(e)}')
            continue

    print('No valid QR code found in any of the processed images.')
    return None


def main():
    """
    Main function to demonstrate usage.
    """
    profiler = Profiler()
    profiler.start()

    parser = argparse.ArgumentParser(
        description='Detect QR codes in a photo set'
    )
    parser.add_argument('folder_path', help='Path to folder containing photos')
    parser.add_argument('--skip', type=int, default=1,
                        help='Check every nth photo (default: 1)')
    parser.add_argument('--showresult', action='store_true',
                        help='Show result with bounding box')
    parser.add_argument('--crop-ratio', type=float, default=1.0,
                        help='Pre-crop ratio for single pass (0.0-1.0, '
                             'based on smaller dimension, default: 1.0)')

    args = parser.parse_args()

    if not os.path.isdir(args.folder_path):
        print(f'Error: {args.folder_path} is not a valid directory')
        return

    result = detect_qr_code_in_photo_set(
        folder_path=args.folder_path,
        skip_interval=args.skip,
        showresult=args.showresult,
        crop_ratio=args.crop_ratio
    )

    if result:
        print(f'\nFinal result: {result}')
    else:
        print('\nNo QR code found in the photo set.')

    profiler.stop()


if __name__ == '__main__':
    main()
