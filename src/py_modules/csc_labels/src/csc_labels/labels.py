# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import glob
import os
import uuid

# ADDITIONAL MODULE IMPORTS ---------------------------------------------------

import qrcode
from PIL import Image


# UTILITY FUNCTIONS -----------------------------------------------------------

def sanitize_path(fp: str = ''):
    """Sanitizes a filepath an returns the result."""
    return os.path.abspath(os.path.realpath(os.path.normpath(fp)))


# ENVIRONMENT VARIABLES -------------------------------------------------------

# directory of this particular file
_HERE = os.path.dirname(sanitize_path(__file__))

# retrieve output directory
_OUTPUTDIR = sanitize_path(os.path.join(_HERE, 'output'))


# FUNCTION DEFINITIONS --------------------------------------------------------


def _divide_chunks(seq: list, n: int):
    """
    Yield successive n-sized chunks from l.
    """
    # looping till length l
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def generate_labels(N: int,
                    cols: int = 3,
                    rows: int = 7,
                    outdir: str = _OUTPUTDIR,
                    qr_size: float = 0.8,
                    error_correction: str = 'L',
                    qr_version: int = 1):
    """
    Create N amount of unique QR-Codes with UUID encoded for A4 label sheets.

    Designed for custom A4 label sheets (3 columns x 7 rows = 21 labels per
    sheet). Each label is 70mm x 42mm (width x height) with 4mm borders on
    top and bottom of the sheet.

    Parameters
    ----------
    N : int
        Number or QR-Codes to generate. Should be a multiple of (cols * rows).
    cols : int
        Columns of the output sheet of QR-Codes (default: 3 for A4 labels).
    rows: int
        Rows of the output sheet of QR-Codes (default: 7 for A4 labels).
    outdir: str
        Output directory for generated QR code sheets.
    qr_size: float
        QR code size control (0.0-1.0 scale). 1.0 corresponds to ~32mm squared
        to fit comfortably on 70mm x 42mm labels. Default: 0.8
    error_correction: str
        Error correction level: 'L' (Low ~7%), 'M' (Medium ~15%), 'Q' (~25%),
        'H' (High ~30%). Lower levels = simpler QR codes. Default: 'L'
    qr_version: int
        QR code version (1-40). Version 1 = simplest (21x21 modules), higher
        versions = more complex but can store more data. Default: 1

    Notes
    -------
    N should be a multiple of (rows * cols)
    QR codes are sized to fit within 70mm x 42mm label dimensions with proper
    margins for printing. Sheet has 4mm borders on top and bottom.
    """

    # Map error correction string to qrcode constant
    error_correction_map = {
        'L': qrcode.constants.ERROR_CORRECT_L,  # ~7% error correction
        'M': qrcode.constants.ERROR_CORRECT_M,  # ~15% error correction
        'Q': qrcode.constants.ERROR_CORRECT_Q,  # ~25% error correction
        'H': qrcode.constants.ERROR_CORRECT_H   # ~30% error correction
    }
    error_correction_level = error_correction_map.get(
        error_correction.upper(), qrcode.constants.ERROR_CORRECT_L)

    # Calculate QR code dimensions based on size parameter
    # Target: 1.0 = ~32mm squared, scaled for 300 DPI
    target_size_mm = 32 * qr_size  # Scale the target size
    target_size_pixels = int(target_size_mm * 300 / 25.4)  # Convert to pixels

    # Calculate box_size for QR code (QR codes are typically square)
    # QR code modules vary by version: Version 1 = 21x21, Version 2 = 25x25
    qr_modules = 21 + (qr_version - 1) * 4  # Calculate modules for version
    box_size = max(1, target_size_pixels // qr_modules)

    # Calculate border size (minimal to maximize QR code area)
    border_size = max(1, int(box_size * 0.1))  # 10% of box_size as border

    qrCodeList = []
    for i in range(0, N):
        uuidTemp = uuid.uuid4()

        # QRCode class with calculated dimensions and complexity settings
        qr = qrcode.QRCode(
            version=qr_version,
            error_correction=error_correction_level,
            box_size=box_size,
            border=border_size,
        )

        # Add only UUID to QR code
        qr.add_data(uuidTemp)
        qr.make(fit=True)

        img = qr.make_image(fill_color='black', back_color='white')
        qrCodeList.append(img)

        # get dimensions of QR-Code image
        widthB, heightB = img.size

    # Divide QR codes into chunks for columns
    qrCodeListChunks = list(_divide_chunks(qrCodeList, cols))

    lineImg = []
    for chunk in qrCodeListChunks:
        # Create a new image for each row
        lineImgTemp = Image.new('RGB',
                                (widthB * cols, heightB),
                                (255, 255, 255))
        # Paste QR codes next to each other
        for index, qr_code in enumerate(chunk):
            lineImgTemp.paste(qr_code, box=(widthB * index, 0), mask=None)
        lineImg.append(lineImgTemp)

    # Divide rows into chunks for pages
    lineImgChunks = list(_divide_chunks(lineImg, rows))

    # Number pages sequentially
    existing_pages = glob.glob(os.path.join(outdir, "*.jpg"))
    page_nr = len(existing_pages) + 1

    for page_index, lines in enumerate(lineImgChunks):
        # Create a new image for each page (A4 size: 210mm × 297mm at 300 DPI)
        # A4 at 300 DPI = 2480 × 3508 pixels
        page_width = 2480   # A4 width in pixels at 300 DPI
        page_height = 3508  # A4 height in pixels at 300 DPI

        pageTemp = Image.new('RGB', (page_width, page_height), (255, 255, 255))

        # Calculate label dimensions in pixels (70mm x 42mm at 300 DPI)
        label_width = int(70 * 300 / 25.4)   # ~827 pixels
        label_height = int(42 * 300 / 25.4)  # ~496 pixels

        # Calculate borders (4mm top and bottom at 300 DPI)
        border_top_bottom = int(4 * 300 / 25.4)  # ~47 pixels

        # Calculate margins to center the label grid horizontally
        # and position with 4mm borders on top and bottom
        margin_x = (page_width - (label_width * cols)) // 2
        margin_y = border_top_bottom  # 4mm border from top

        # Get the QR codes for this page
        page_start_index = page_index * rows
        page_qr_codes = qrCodeList[page_start_index:page_start_index +
                                   (rows * cols)]

        # Paste QR codes in grid layout
        for row_index in range(rows):
            y_pos = margin_y + (label_height * row_index)
            for col_index in range(cols):
                qr_index = row_index * cols + col_index
                if qr_index < len(page_qr_codes):
                    qr_code = page_qr_codes[qr_index]
                    x_pos = margin_x + (label_width * col_index)
                    # Center QR code within each label
                    qr_x = x_pos + (label_width - widthB) // 2
                    qr_y = y_pos + (label_height - heightB) // 2
                    pageTemp.paste(qr_code, box=(qr_x, qr_y), mask=None)

        # Save the page
        imgName = sanitize_path(os.path.join(outdir, f'{page_nr}.jpg'))
        pageTemp.save(imgName, 'JPEG', quality=95, DPI=(300, 300))
        page_nr += 1


# MAIN ROUTINE ----------------------------------------------------------------

if __name__ == '__main__':
    # Generate 21 QR codes (1 full sheet) with simple settings
    generate_labels(21, qr_size=0.4, error_correction='L', qr_version=1)

    # Examples for even simpler QR codes:

    # Simplest
    # generate_labels(21, qr_size=0.33, error_correction='L', qr_version=1)

    # Simple
    # generate_labels(21, qr_size=0.5, error_correction='M', qr_version=1)

    # Complex
    # generate_labels(21, qr_size=0.8, error_correction='H', qr_version=2)
