# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import argparse
import glob
import os
import sys
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
                    qr_size: float = 0.5,
                    error_correction: str = 'L',
                    qr_version: int = 1,
                    adaptive_layout: bool = False):
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
        to fit comfortably on 70mm x 42mm labels. Default: 0.5
    error_correction: str
        Error correction level: 'L' (Low ~7%), 'M' (Medium ~15%), 'Q' (~25%),
        'H' (High ~30%). Lower levels = simpler QR codes. Default: 'L'
    qr_version: int
        QR code version (1-40). Version 1 = simplest (21x21 modules), higher
        versions = more complex but can store more data. Default: 1
    adaptive_layout: bool
        If True, ignores fixed label sizes and spreads QR codes evenly across
        the page, only respecting top and bottom borders. Default: False

    Notes
    -------
    N should be a multiple of (rows * cols)
    QR codes are sized to fit within 70mm x 42mm label dimensions with proper
    margins for printing. Sheet has 4mm borders on top and bottom.
    """

    print("Starting QR code generation...")
    print(f"  - Count: {N} QR codes")
    print(f"  - Layout: {cols} columns × {rows} rows")
    print(f"  - Output directory: {outdir}")
    print(f"  - QR size: {qr_size}")
    print(f"  - Error correction: {error_correction}")
    print(f"  - QR version: {qr_version}")
    print(f"  - Adaptive layout: {adaptive_layout}")

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

    print(f"Generating {N} individual QR codes...")
    qrCodeList = []
    uuidList = []
    for i in range(0, N):
        if i % 10 == 0:  # Progress update every 10 QR codes
            print(f"  Generated {i}/{N} QR codes...")

        uuidTemp = uuid.uuid4()
        uuidList.append(str(uuidTemp))

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

        img = qr.make_image(
            fill_color='black', back_color='white').convert('RGB')
        qrCodeList.append(img)

        # get dimensions of QR-Code image
        widthB, heightB = img.size

    print(f"  Completed generating all {N} QR codes!")

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

    print(f"Creating {len(lineImgChunks)} label sheets...")
    print(f"  Starting from page number: {page_nr}")

    for page_index, lines in enumerate(lineImgChunks):
        print(f"  Creating page {page_index + 1}/{len(lineImgChunks)}...")
        # Create a new image for each page (A4 size: 210mm × 297mm at 300 DPI)
        # A4 at 300 DPI = 2480 × 3508 pixels
        page_width = 2480   # A4 width in pixels at 300 DPI
        page_height = 3508  # A4 height in pixels at 300 DPI

        pageTemp = Image.new('RGB', (page_width, page_height), (255, 255, 255))

        # Calculate borders (4mm top and bottom at 300 DPI)
        border_top_bottom = int(4 * 300 / 25.4)  # ~47 pixels

        if adaptive_layout:
            # Adaptive layout: spread QR codes evenly across the page
            # Available height = page height minus top and bottom borders
            available_height = page_height - (2 * border_top_bottom)
            available_width = page_width

            # Calculate cell dimensions based on rows and cols
            cell_width = available_width // cols
            cell_height = available_height // rows

            margin_x = 0
            margin_y = border_top_bottom
        else:
            # Fixed layout: use standard label dimensions (70mm x 42mm)
            label_width = int(70 * 300 / 25.4)   # ~827 pixels
            label_height = int(42 * 300 / 25.4)  # ~496 pixels

            cell_width = label_width
            cell_height = label_height

            # Calculate margins to center the label grid horizontally
            margin_x = (page_width - (cell_width * cols)) // 2
            margin_y = border_top_bottom  # 4mm border from top

        # Get the QR codes for this page
        codes_per_page = rows * cols
        page_start_index = page_index * codes_per_page
        page_qr_codes = qrCodeList[page_start_index:page_start_index +
                                   codes_per_page]

        # Paste QR codes in grid layout
        for row_index in range(rows):
            y_pos = margin_y + (cell_height * row_index)
            for col_index in range(cols):
                qr_index = row_index * cols + col_index
                if qr_index < len(page_qr_codes):
                    qr_code = page_qr_codes[qr_index]
                    x_pos = margin_x + (cell_width * col_index)
                    # Center QR code within each cell
                    qr_x = x_pos + (cell_width - widthB) // 2
                    qr_y = y_pos + (cell_height - heightB) // 2
                    pageTemp.paste(qr_code, box=(qr_x, qr_y), mask=None)

        # Save the page image
        imgName = sanitize_path(os.path.join(outdir, f'{page_nr}.jpg'))
        try:
            pageTemp.save(imgName, 'JPEG', quality=95, DPI=(300, 300))
            print(f"    Saved: {imgName}")
        except Exception as e:
            print(f"    ERROR: Failed to save {imgName} - {e}")
            raise

        # Save the UUID list for this page
        txtName = sanitize_path(os.path.join(outdir, f'{page_nr}.txt'))
        page_end_index = page_start_index + codes_per_page
        page_uuids = uuidList[page_start_index:page_end_index]
        try:
            with open(txtName, 'w') as f:
                for uid in page_uuids:
                    f.write(f'{uid}\n')
            print(f"    Saved: {txtName}")
        except Exception as e:
            print(f"    ERROR: Failed to save {txtName} - {e}")
            raise

        page_nr += 1

    print(f"Successfully generated {N} QR codes in "
          f"{len(lineImgChunks)} sheets!")
    print(f"Output directory: {outdir}")
    print(f"Files created: {page_nr - len(existing_pages) - 1} new sheets "
          f"(JPG + TXT each)")


# COMMAND LINE INTERFACE ------------------------------------------------------

def create_cli_parser():
    """Create and configure the command line argument parser."""
    parser = argparse.ArgumentParser(
        description='Generate QR code labels for A4 sheets with '
                    'UUID encoding.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Generate 21 QR codes with default settings
  python labels.py 21

  # Generate 42 QR codes with custom settings
  python labels.py 42 --qr-size 0.8 --error-correction H --qr-version 2

  # Generate 63 QR codes to custom output directory
  python labels.py 63 --output-dir /path/to/output

  # Generate simplest possible QR codes
  python labels.py 21 --qr-size 0.33 --error-correction L --qr-version 1
        '''
    )

    parser.add_argument(
        'count',
        type=int,
        help='Number of QR codes to generate (should be multiple of 21 for '
             'full sheets)'
    )

    parser.add_argument(
        '--qr-size',
        type=float,
        default=0.7,
        help='QR code size control (0.0-1.0 scale). 1.0 corresponds to '
             '~32mm squared. Default: 0.7'
    )

    parser.add_argument(
        '--error-correction',
        choices=['L', 'M', 'Q', 'H'],
        default='L',
        help='Error correction level: L (Low ~7%%), M (Medium ~15%%), '
             'Q (~25%%), H (High ~30%%). Default: L'
    )

    parser.add_argument(
        '--qr-version',
        type=int,
        default=1,
        choices=range(1, 41),
        metavar='1-40',
        help='QR code version (1-40). Version 1 = simplest (21x21 modules). '
             'Default: 1'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default=_OUTPUTDIR,
        help=f'Output directory for generated QR code sheets. '
             f'Default: {_OUTPUTDIR}'
    )

    parser.add_argument(
        '--cols',
        type=int,
        default=3,
        help='Number of columns per sheet. Default: 3'
    )

    parser.add_argument(
        '--rows',
        type=int,
        default=7,
        help='Number of rows per sheet. Default: 7'
    )

    parser.add_argument(
        '--adaptive-layout',
        action='store_true',
        help='Spread QR codes evenly across the page, ignoring fixed label '
             'sizes. Only respects top and bottom page borders.'
    )

    return parser


def main():
    """Main CLI entry point."""
    print("CSC Labels - CLI Mode")

    try:
        parser = create_cli_parser()
        args = parser.parse_args()
        print(f"Parsed arguments: {vars(args)}")

        # Validate count is positive
        if args.count <= 0:
            print('ERROR: Count must be a positive integer.',
                  file=sys.stderr)
            sys.exit(1)

        # Validate qr_size is in valid range
        if not args.adaptive_layout and (not 0.0 <= args.qr_size <= 1.0):
            print(
                'ERROR: Without adaptive layout QR size must be '
                'between 0.0 and 1.0.',
                file=sys.stderr)
            sys.exit(1)

        # Create output directory if it doesn't exist
        output_dir = sanitize_path(args.output_dir)
        print(f"Creating output directory: {output_dir}")
        os.makedirs(output_dir, exist_ok=True)

        # Generate labels with CLI arguments
        print("Starting QR code generation...")
        generate_labels(
            N=args.count,
            cols=args.cols,
            rows=args.rows,
            outdir=output_dir,
            qr_size=args.qr_size,
            error_correction=args.error_correction,
            qr_version=args.qr_version,
            adaptive_layout=args.adaptive_layout
        )
        print(f'CLI: Successfully generated {args.count} QR codes in '
              f'{output_dir}')

    except SystemExit:
        # Re-raise SystemExit to preserve exit codes
        raise
    except Exception as e:
        print(f'CLI ERROR: Unexpected error - {e}', file=sys.stderr)
        print(f'Error type: {type(e).__name__}', file=sys.stderr)
        import traceback
        print('Full traceback:', file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


# MAIN ROUTINE ----------------------------------------------------------------

if __name__ == '__main__':
    print("CSC Labels - QR Code Generator starting...")

    try:
        # Check if any command line arguments were provided
        if len(sys.argv) > 1:
            print(f"Using CLI interface with arguments: "
                  f"{' '.join(sys.argv[1:])}")
            # Use CLI interface
            main()
        else:
            print("No arguments provided, using default behavior...")
            print("Generating 21 QR codes with default settings...")
            # Use original behavior - generate 21 QR codes with defaults
            generate_labels(21, qr_size=0.7, error_correction='L',
                            qr_version=1)
            print("Successfully generated 21 QR codes!")

    except ImportError as e:
        print(f"ERROR: Missing required module - {e}")
        print("Please install requirements: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected error occurred - {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print("Full traceback:")
        traceback.print_exc()
        sys.exit(1)
