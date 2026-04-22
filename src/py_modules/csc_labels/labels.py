# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import argparse
import datetime
import glob
import math
import os
import sys
import tempfile
import uuid

# ADDITIONAL MODULE IMPORTS ---------------------------------------------------

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.image.styledpil import StyledPilImage


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


def _mm_to_px(mm: float, dpi: int = 300) -> int:
    """Convert millimeters to pixels at the given DPI."""
    return int(round(mm * dpi / 25.4))


def _compute_vertical_margin(page_height: int,
                             grid_height: int,
                             dead_top: int,
                             dead_bottom: int) -> int:
    """
    Compute top margin for grid placement.

    Uses dead zones when they can be respected. If the label grid is taller
    than the dead-zone-constrained printable area, falls back to full-page
    centering to avoid consistent vertical offset.
    """
    available_height = page_height - dead_top - dead_bottom
    if grid_height <= available_height:
        return dead_top + ((available_height - grid_height) // 2)
    return max(0, (page_height - grid_height) // 2)


def _read_text_lines(filepath: str):
    """Read non-empty stripped lines from a text file."""
    resolved = sanitize_path(filepath)
    with open(resolved, 'r', encoding='utf-8') as handle:
        return [line.strip() for line in handle if line.strip()]


def _build_base_names(base_name: str, count: int, start_index: int = 1):
    """Generate indexed names with zero-padding based on index range."""
    last_index = start_index + count - 1
    pad_width = max(2, len(str(last_index)))
    return [
        f"{base_name}_{idx:0{pad_width}d}"
        for idx in range(start_index, last_index + 1)
    ]


def _build_output_stem(base_name: str,
                       start_index: int,
                       end_index: int,
                       pad_width: int = 3):
    """Build output stem like YYMMDD_BASE_001-021."""
    date_prefix = datetime.datetime.now().strftime('%y%m%d')
    safe_base = ''.join(
        char if char.isalnum() or char in ('-', '_') else '_'
        for char in base_name.strip().upper()
    )
    return (
        f"{date_prefix}_{safe_base}_"
        f"{start_index:0{pad_width}d}-{end_index:0{pad_width}d}"
    )


def _build_label_payloads(N: int,
                          uuid_file: str = None,
                          name_file: str = None,
                          base_name: str = None,
                          start_index: int = 1):
    """
    Build UUID and name lists for label generation.

    If uuid_file is provided, UUIDs are read from file (one per line).
    Otherwise random UUIDs are generated.
    If name_file is provided, names are read from file (one per line).
    If base_name is provided, names are auto-generated as:
    <base_name>_<index with zero padding>.
    """
    if uuid_file:
        uuid_values = _read_text_lines(uuid_file)
        if len(uuid_values) < N:
            raise ValueError(
                f"UUID file contains {len(uuid_values)} rows but "
                f"{N} are required."
            )
        uuid_values = uuid_values[:N]
    else:
        uuid_values = [str(uuid.uuid4()) for _ in range(N)]

    if name_file:
        name_values = _read_text_lines(name_file)
        if len(name_values) < N:
            raise ValueError(
                f"Name file contains {len(name_values)} rows but "
                f"{N} are required."
            )
        name_values = name_values[:N]
    elif base_name:
        name_values = _build_base_names(
            base_name=base_name,
            count=N,
            start_index=start_index
        )
    else:
        name_values = [None] * N

    return uuid_values, name_values


def _load_font(size: int):
    """Load a readable truetype font with fallback to PIL default."""
    pil_fonts_dir = os.path.join(
        os.path.dirname(ImageFont.__file__),
        'fonts'
    )
    candidates = [
        'arial.ttf',
        'DejaVuSans.ttf',
        r'C:\Windows\Fonts\arial.ttf',
        r'C:\Windows\Fonts\segoeui.ttf',
        os.path.join(pil_fonts_dir, 'DejaVuSans.ttf'),
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_font_size(text: str, max_width: int, max_height: int,
                   start_size: int, min_size: int = 10):
    """Find the largest readable font size that fits in a box."""
    dummy = Image.new('RGB', (1, 1), (255, 255, 255))
    draw = ImageDraw.Draw(dummy)
    for size in range(start_size, min_size - 1, -1):
        font = _load_font(size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        width = right - left
        height = bottom - top
        if width <= max_width and height <= max_height:
            return font
    return _load_font(min_size)


def _is_truetype_font(font) -> bool:
    """Return True when font supports scalable truetype sizing."""
    return font.__class__.__name__ == 'FreeTypeFont'


def _draw_centered_text_in_box(image: Image.Image,
                               text: str,
                               box_x: int,
                               box_y: int,
                               box_w: int,
                               box_h: int,
                               start_size: int,
                               min_size: int = 8,
                               fill=(0, 0, 0),
                               valign: str = 'center'):
    """
    Draw centered text in a box with optional vertical alignment.

    If truetype fonts are unavailable, uses bitmap text upscaling so output
    still becomes visibly larger instead of staying tiny.
    """
    if not text or box_w <= 2 or box_h <= 2:
        return

    draw = ImageDraw.Draw(image)
    font = _fit_font_size(
        text=text,
        max_width=box_w,
        max_height=box_h,
        start_size=start_size,
        min_size=min_size
    )
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = max(1, bbox[2] - bbox[0])
    text_h = max(1, bbox[3] - bbox[1])
    text_x = box_x + ((box_w - text_w) // 2)
    if valign == 'top':
        target_y = box_y
    elif valign == 'bottom':
        target_y = box_y + box_h - text_h
    else:
        target_y = box_y + ((box_h - text_h) // 2)

    if _is_truetype_font(font):
        # Offset by bbox origin to avoid extra apparent padding from font
        # internal ascender/descender metrics.
        text_y = target_y - bbox[1]
        draw.text((text_x, text_y), text, fill=fill, font=font)
        return

    # Bitmap fallback: scale rendered mask to requested box.
    scale = max(1, int(min(box_w / text_w, box_h / text_h)))
    if scale <= 1:
        text_y = target_y - bbox[1]
        draw.text((text_x, text_y), text, fill=fill, font=font)
        return

    mask = Image.new('L', (text_w, text_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.text((-bbox[0], -bbox[1]), text, fill=255, font=font)
    scaled_mask = mask.resize((text_w * scale, text_h * scale),
                              Image.Resampling.NEAREST)
    paste_x = box_x + ((box_w - scaled_mask.width) // 2)
    if valign == 'top':
        paste_y = box_y
    elif valign == 'bottom':
        paste_y = box_y + box_h - scaled_mask.height
    else:
        paste_y = box_y + ((box_h - scaled_mask.height) // 2)
    image.paste(fill, (paste_x, paste_y), scaled_mask)


def _split_uuid_on_third_dash(uuid_text: str):
    """Split UUID into two lines at the third dash."""
    parts = uuid_text.split('-')
    if len(parts) >= 5:
        first_line = '-'.join(parts[:3])
        second_line = '-'.join(parts[3:])
        return first_line, second_line

    midpoint = max(1, len(uuid_text) // 2)
    return uuid_text[:midpoint], uuid_text[midpoint:]


def _split_name_two_lines(name_text: str):
    """Split a name into two lines at a natural separator."""
    for sep in ['_', '-', ' ']:
        if sep in name_text:
            parts = name_text.split(sep)
            if len(parts) >= 2:
                left = sep.join(parts[:-1])
                right = parts[-1]
                if left and right:
                    return left, right
    midpoint = max(1, len(name_text) // 2)
    return name_text[:midpoint], name_text[midpoint:]


def _compose_standard_qr_tile(qr_img: Image.Image, label_text: str = None):
    """Create a standard QR tile with optional readable text below QR."""
    if not label_text:
        return qr_img

    text_area = max(_mm_to_px(4.0), int(qr_img.height * 0.2))
    tile = Image.new('RGB', (qr_img.width, qr_img.height + text_area),
                     (255, 255, 255))
    tile.paste(qr_img, (0, 0))

    draw = ImageDraw.Draw(tile)
    font = _fit_font_size(
        text=label_text,
        max_width=qr_img.width - 8,
        max_height=text_area - 4,
        start_size=max(12, text_area - 8),
    )
    bbox = draw.textbbox((0, 0), label_text, font=font)
    txt_w = bbox[2] - bbox[0]
    txt_h = bbox[3] - bbox[1]
    txt_x = (qr_img.width - txt_w) // 2
    txt_y = qr_img.height + max(1, (text_area - txt_h) // 2)
    draw.text((txt_x, txt_y), label_text, fill=(0, 0, 0), font=font)
    return tile


def _fit_two_line_font(draw: ImageDraw.ImageDraw,
                       line_1: str,
                       line_2: str,
                       max_width: int,
                       max_height: int,
                       start_size: int = 14,
                       min_size: int = 6,
                       line_gap: int = 2):
    """Fit two lines of text into a bounded area."""
    for size in range(start_size, min_size - 1, -1):
        font = _load_font(size)
        b1 = draw.textbbox((0, 0), line_1, font=font)
        b2 = draw.textbbox((0, 0), line_2, font=font)
        w1 = b1[2] - b1[0]
        h1 = b1[3] - b1[1]
        w2 = b2[2] - b2[0]
        h2 = b2[3] - b2[1]
        total_h = h1 + h2 + line_gap
        if w1 <= max_width and w2 <= max_width and total_h <= max_height:
            return font, w1, h1, w2, h2, total_h

    font = _load_font(min_size)
    b1 = draw.textbbox((0, 0), line_1, font=font)
    b2 = draw.textbbox((0, 0), line_2, font=font)
    w1 = b1[2] - b1[0]
    h1 = b1[3] - b1[1]
    w2 = b2[2] - b2[0]
    h2 = b2[3] - b2[1]
    total_h = h1 + h2 + line_gap
    return font, w1, h1, w2, h2, total_h


def generate_labels(N: int,
                    cols: int = 3,
                    rows: int = 7,
                    outdir: str = _OUTPUTDIR,
                    qr_size: float = 0.5,
                    error_correction: str = 'L',
                    qr_version: int = 1,
                    adaptive_layout: bool = False,
                    uuid_file: str = None,
                    name_file: str = None,
                    base_name: str = None,
                    start_index: int = 1):
    """
    Create N amount of unique QR-Codes with UUID encoded for A4 label sheets.

    Designed for custom A4 label sheets (3 columns x 7 rows = 21 labels per
    sheet). Each label is 70mm x 42mm (width x height) with 4mm dead zones on
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
    margins for printing. Sheet has 4mm dead zones on top and bottom.
    """

    print("Starting QR code generation...")
    print(f"  - Count: {N} QR codes")
    print(f"  - Layout: {cols} columns × {rows} rows")
    print(f"  - Output directory: {outdir}")
    print(f"  - QR size: {qr_size}")
    print(f"  - Error correction: {error_correction}")
    print(f"  - QR version: {qr_version}")
    print(f"  - Adaptive layout: {adaptive_layout}")
    if uuid_file:
        print(f"  - UUID file: {uuid_file}")
    if name_file:
        print(f"  - Name file: {name_file}")
    if base_name:
        print(f"  - Base name: {base_name}")
        print(f"  - Start index: {start_index}")

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
    # Keep extra margin in non-NFC labels for UUID/name text areas.
    target_size_mm = target_size_mm * 0.8
    target_size_pixels = int(target_size_mm * 300 / 25.4)  # Convert to pixels

    # Calculate box_size for QR code (QR codes are typically square)
    # QR code modules vary by version: Version 1 = 21x21, Version 2 = 25x25
    qr_modules = 21 + (qr_version - 1) * 4  # Calculate modules for version
    box_size = max(1, target_size_pixels // qr_modules)

    # Calculate border size (minimal to maximize QR code area)
    border_size = max(1, int(box_size * 0.1))  # 10% of box_size as border

    print(f"Generating {N} individual QR codes...")
    qrCodeList = []
    uuidList, nameList = _build_label_payloads(
        N=N,
        uuid_file=uuid_file,
        name_file=name_file,
        base_name=base_name,
        start_index=start_index
    )
    for i in range(0, N):
        if i % 10 == 0:  # Progress update every 10 QR codes
            print(f"  Generated {i}/{N} QR codes...")

        uuid_value = uuidList[i]
        label_text = nameList[i]

        # QRCode class with calculated dimensions and complexity settings
        qr = qrcode.QRCode(
            version=qr_version,
            error_correction=error_correction_level,
            box_size=box_size,
            border=border_size,
        )

        # Add only UUID to QR code
        qr.add_data(uuid_value)
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

        # Calculate dead zones (4mm top and bottom at 300 DPI)
        border_top_bottom = int(4 * 300 / 25.4)

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
            margin_y = _compute_vertical_margin(
                page_height=page_height,
                grid_height=cell_height * rows,
                dead_top=border_top_bottom,
                dead_bottom=border_top_bottom
            )

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
                    absolute_index = page_start_index + qr_index
                    uuid_value = uuidList[absolute_index]
                    label_text = nameList[absolute_index]
                    x_pos = margin_x + (cell_width * col_index)
                    # Center QR code within each cell
                    qr_x = x_pos + (cell_width - widthB) // 2
                    qr_y = y_pos + (cell_height - heightB) // 2
                    # Slight upward correction to balance top/bottom margins.
                    qr_y -= _mm_to_px(1.4)
                    qr_y = max(y_pos, min(qr_y, y_pos + cell_height - heightB))
                    pageTemp.paste(qr_code, box=(qr_x, qr_y), mask=None)

                    # Draw UUID above QR as one row, constrained to cell.
                    uuid_text = str(uuid_value)
                    # Shared spacing control between QR and both text bands
                    # in non-NFC labels.
                    text_padding = _mm_to_px(1.5)
                    shared_text_max_height = _mm_to_px(8.0)
                    top_band_top = y_pos + text_padding
                    top_band_bottom = qr_y - text_padding
                    uuid_max_width = max(
                        10,
                        min(cell_width - 8, int(widthB * 1.8))
                    )
                    top_band_height = top_band_bottom - top_band_top
                    if top_band_height > 8:
                        uuid_max_height = max(
                            10,
                            min(top_band_height, shared_text_max_height)
                        )
                        box_x = x_pos + ((cell_width - uuid_max_width) // 2)
                        box_y = top_band_bottom - uuid_max_height
                        _draw_centered_text_in_box(
                            image=pageTemp,
                            text=uuid_text,
                            box_x=box_x,
                            box_y=box_y,
                            box_w=uuid_max_width,
                            box_h=uuid_max_height,
                            start_size=36,
                            min_size=15,
                            fill=(0, 0, 0),
                            valign='bottom'
                        )

                    # Draw optional human-readable label
                    # below QR in cell bounds.
                    if label_text:
                        bottom_band_top = qr_y + heightB + text_padding
                        bottom_band_bottom = y_pos + cell_height - text_padding
                        bottom_band_height = (bottom_band_bottom -
                                              bottom_band_top)
                        if bottom_band_height > 8:
                            # Allow a taller text band for the human-readable
                            # name so it renders noticeably larger than the
                            # UUID row above the QR.
                            name_text_max_height = _mm_to_px(11.0)
                            # Keep names readable but strictly bounded in
                            # standard (non-NFC) labels.
                            name_max_width = max(
                                10,
                                min(cell_width - 8, int(widthB * 2.2))
                            )
                            # Hard clamp vertical text size to avoid oversized
                            # output when bitmap-font fallback is active.
                            name_max_height = max(
                                10,
                                min(bottom_band_height, name_text_max_height)
                            )
                            box_x = (
                                x_pos + ((cell_width - name_max_width) // 2)
                            )
                            box_y = bottom_band_top
                            _draw_centered_text_in_box(
                                image=pageTemp,
                                text=label_text,
                                box_x=box_x,
                                box_y=box_y,
                                box_w=name_max_width,
                                box_h=name_max_height,
                                start_size=56,
                                min_size=20,
                                fill=(0, 0, 0),
                                valign='top'
                            )

        page_end_index = page_start_index + codes_per_page
        page_uuids = uuidList[page_start_index:page_end_index]
        range_start = start_index + page_start_index
        range_end = range_start + len(page_uuids) - 1
        range_pad_width = max(3, len(str(start_index + N - 1)))
        if base_name:
            file_stem = _build_output_stem(
                base_name=base_name,
                start_index=range_start,
                end_index=range_end,
                pad_width=range_pad_width
            )
        else:
            file_stem = str(page_nr)

        # Save the page image
        imgName = sanitize_path(os.path.join(outdir, f'{file_stem}.jpg'))
        try:
            pageTemp.save(imgName, 'JPEG', quality=95, DPI=(300, 300))
            print(f"    Saved: {imgName}")
        except Exception as e:
            print(f"    ERROR: Failed to save {imgName} - {e}")
            raise

        pdfName = sanitize_path(os.path.join(outdir, f'{file_stem}.pdf'))
        try:
            pageTemp.save(
                pdfName,
                'PDF',
                resolution=300.0,
                quality=100,
                subsampling=0
            )
            print(f"    Saved: {pdfName}")
        except Exception as e:
            print(f"    ERROR: Failed to save {pdfName} - {e}")
            raise

        # Save the UUID list for this page
        txtName = sanitize_path(os.path.join(outdir, f'{file_stem}.txt'))
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


def generate_nfc_labels(N: int,
                        cols: int = 3,
                        rows: int = 7,
                        outdir: str = _OUTPUTDIR,
                        qr_size_mm: float = 21.0,
                        outer_circle_mm: float = 30.0,
                        center_blank_mm: float = 5.0,
                        uuid_file: str = None,
                        name_file: str = None,
                        base_name: str = None,
                        start_index: int = 1):
    """
    Generate NFC label sheets with fixed physical dimensions.

    Each label gets:
    - A QR code centered in the label (same grid behavior as default routine)
    - QR code printed at qr_size_mm x qr_size_mm
    - A outer_circle_mm circle outline around the QR code
    - A center_blank_mm blank circle at the QR center
      (via StyledPilImage embedding)
    """
    print("Starting NFC QR code generation...")
    print(f"  - Count: {N} QR codes")
    print(f"  - Layout: {cols} columns × {rows} rows")
    print(f"  - Output directory: {outdir}")

    dpi = 300
    qr_size_px = _mm_to_px(qr_size_mm, dpi=dpi)
    outer_circle_px = _mm_to_px(outer_circle_mm, dpi=dpi)
    center_blank_px = _mm_to_px(center_blank_mm, dpi=dpi)

    print(f"  - QR size: {qr_size_mm}mm ({qr_size_px}px at {dpi} DPI)")
    print(f"  - Outer circle: {outer_circle_mm}mm ({outer_circle_px}px)")
    print(f"  - Center blank: {center_blank_mm}mm ({center_blank_px}px)")
    if uuid_file:
        print(f"  - UUID file: {uuid_file}")
    if name_file:
        print(f"  - Name file: {name_file}")
    if base_name:
        print(f"  - Base name: {base_name}")
        print(f"  - Start index: {start_index}")

    qrCodeList = []
    uuidList, nameList = _build_label_payloads(
        N=N,
        uuid_file=uuid_file,
        name_file=name_file,
        base_name=base_name,
        start_index=start_index
    )

    # Create a temporary "logo" image for StyledPilImage center embedding.
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_logo:
        logo_path = tmp_logo.name

    try:
        logo_canvas = Image.new('RGBA', (center_blank_px, center_blank_px),
                                (0, 0, 0, 0))
        logo_draw = ImageDraw.Draw(logo_canvas)
        logo_draw.ellipse((0, 0, center_blank_px - 1, center_blank_px - 1),
                          fill=(255, 255, 255, 255))
        logo_canvas.save(logo_path, 'PNG')

        print(f"Generating {N} NFC QR codes...")
        for i in range(N):
            if i % 10 == 0:
                print(f"  Generated {i}/{N} QR codes...")

            uuid_value = uuidList[i]
            label_text = nameList[i]

            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=20,
                border=4,
            )
            qr.add_data(str(uuid_value))
            qr.make(fit=True)

            qr_img = qr.make_image(
                image_factory=StyledPilImage,
                embedded_image_path=logo_path
            ).convert('RGB')

            # Enforce exact printed size using nearest-neighbor
            # to preserve module edges.
            qr_img = qr_img.resize(
                (qr_size_px, qr_size_px),
                Image.Resampling.NEAREST
            )

            # Ensure exactly 5mm blank circle at center.
            qr_draw = ImageDraw.Draw(qr_img)
            half_blank = center_blank_px // 2
            qr_center_x = qr_size_px // 2
            qr_center_y = qr_size_px // 2
            qr_draw.ellipse(
                (
                    qr_center_x - half_blank,
                    qr_center_y - half_blank,
                    qr_center_x + half_blank,
                    qr_center_y + half_blank,
                ),
                fill=(255, 255, 255)
            )

            # Build a tile that includes the 30mm grey outlined circle.
            tile_size = max(outer_circle_px, qr_size_px)
            tile = Image.new('RGB', (tile_size, tile_size), (255, 255, 255))
            tile_draw = ImageDraw.Draw(tile)
            circle_pad = (tile_size - outer_circle_px) // 2
            tile_draw.ellipse(
                (
                    circle_pad,
                    circle_pad,
                    circle_pad + outer_circle_px - 1,
                    circle_pad + outer_circle_px - 1,
                ),
                outline=(170, 170, 170),
                width=max(1, _mm_to_px(0.2, dpi=dpi))
            )

            qr_offset = (tile_size - qr_size_px) // 2
            tile.paste(qr_img, (qr_offset, qr_offset))

            # Draw UUID above the QR code, constrained to the circle.
            uuid_text = str(uuid_value)
            circle_center = tile_size / 2.0
            circle_radius = outer_circle_px / 2.0
            circle_top = circle_pad
            qr_top = qr_offset
            uuid_text_top = circle_top + 2
            uuid_text_bottom = qr_top - 1

            if uuid_text_bottom > uuid_text_top:
                y_reference = uuid_text_bottom - 1
                dy = abs(y_reference - circle_center)
                half_chord = math.sqrt(
                    max(0.0, circle_radius ** 2 - dy ** 2)
                )
                max_uuid_width = max(10, int(2 * half_chord) - 6)
                max_uuid_height = max(8, int(uuid_text_bottom - uuid_text_top))
                uuid_line_1, uuid_line_2 = _split_uuid_on_third_dash(uuid_text)
                line_gap = 6

                uuid_font = None
                line_1_h = 0
                line_2_h = 0
                line_1_w = 0
                line_2_w = 0
                tile_draw = ImageDraw.Draw(tile)
                max_start_size = max(9, min(15, (max_uuid_height // 2) + 1))
                for size in range(max_start_size, 5, -1):
                    candidate_font = _load_font(size)
                    b1 = tile_draw.textbbox(
                        (0, 0), uuid_line_1, font=candidate_font
                    )
                    b2 = tile_draw.textbbox(
                        (0, 0), uuid_line_2, font=candidate_font
                    )
                    c_line_1_w = b1[2] - b1[0]
                    c_line_1_h = b1[3] - b1[1]
                    c_line_2_w = b2[2] - b2[0]
                    c_line_2_h = b2[3] - b2[1]
                    total_h = c_line_1_h + c_line_2_h + line_gap
                    if (
                        c_line_1_w <= max_uuid_width and
                        c_line_2_w <= max_uuid_width and
                        total_h <= max_uuid_height
                    ):
                        uuid_font = candidate_font
                        line_1_h = c_line_1_h
                        line_2_h = c_line_2_h
                        line_1_w = c_line_1_w
                        line_2_w = c_line_2_w
                        break

                if uuid_font is None:
                    uuid_font = _load_font(7)
                    b1 = tile_draw.textbbox(
                        (0, 0),
                        uuid_line_1,
                        font=uuid_font
                    )
                    b2 = tile_draw.textbbox(
                        (0, 0),
                        uuid_line_2,
                        font=uuid_font
                    )
                    line_1_w = b1[2] - b1[0]
                    line_1_h = b1[3] - b1[1]
                    line_2_w = b2[2] - b2[0]
                    line_2_h = b2[3] - b2[1]

                total_h = line_1_h + line_2_h + line_gap
                line_1_x = int(circle_center - (line_1_w / 2))
                line_2_x = int(circle_center - (line_2_w / 2))
                line_1_y = int(uuid_text_bottom - total_h)
                line_2_y = int(line_1_y + line_1_h + line_gap)

                tile_draw.text(
                    (line_1_x, line_1_y),
                    uuid_line_1,
                    fill=(0, 0, 0),
                    font=uuid_font
                )
                tile_draw.text(
                    (line_2_x, line_2_y),
                    uuid_line_2,
                    fill=(0, 0, 0),
                    font=uuid_font
                )

            if label_text:
                circle_bottom = circle_pad + outer_circle_px
                qr_bottom = qr_offset + qr_size_px
                # Keep text visually close to the QR
                # while staying in the circle.
                text_top = qr_bottom
                text_bottom = circle_bottom - 2

                if text_bottom > text_top:
                    # Limit width at the top of the text band where the text
                    # starts so the rendered name remains inside the circle.
                    y_reference = text_top + 1
                    dy = abs(y_reference - circle_center)
                    half_chord = math.sqrt(
                        max(0.0, circle_radius ** 2 - dy ** 2)
                    )
                    circle_limited_width = max(10, int(2 * half_chord) - 6)
                    # Keep label text visually compact under the QR code.
                    qr_limited_width = max(10, int(qr_size_px * 0.72))
                    max_text_width = min(
                        circle_limited_width,
                        qr_limited_width
                    )
                    max_text_height = max(10, int(text_bottom - text_top))

                    font = _fit_font_size(
                        text=label_text,
                        max_width=max_text_width,
                        max_height=max_text_height,
                        start_size=max(12, max_text_height),
                    )
                    tile_draw = ImageDraw.Draw(tile)
                    bbox = tile_draw.textbbox((0, 0), label_text, font=font)
                    txt_w = bbox[2] - bbox[0]
                    txt_x = int(circle_center - (txt_w / 2))
                    txt_y = int(text_top + 1)
                    tile_draw.text((txt_x, txt_y), label_text,
                                   fill=(0, 0, 0), font=font)

            qrCodeList.append(tile)

        print(f"  Completed generating all {N} NFC QR codes!")

    finally:
        if os.path.exists(logo_path):
            os.unlink(logo_path)

    existing_pages = glob.glob(os.path.join(outdir, "*.jpg"))
    page_nr = len(existing_pages) + 1
    codes_per_page = rows * cols
    page_chunks = list(_divide_chunks(qrCodeList, codes_per_page))

    page_width = 2480
    page_height = 3508
    border_top_bottom = _mm_to_px(4.0, dpi=dpi)
    label_width = _mm_to_px(70.0, dpi=dpi)
    label_height = _mm_to_px(42.0, dpi=dpi)
    margin_x = (page_width - (label_width * cols)) // 2
    margin_y = _compute_vertical_margin(
        page_height=page_height,
        grid_height=label_height * rows,
        dead_top=border_top_bottom,
        dead_bottom=border_top_bottom
    )

    print(f"Creating {len(page_chunks)} NFC label sheets...")
    for page_index, page_qr_codes in enumerate(page_chunks):
        print(f"  Creating page {page_index + 1}/{len(page_chunks)}...")
        pageTemp = Image.new('RGB', (page_width, page_height), (255, 255, 255))

        for row_index in range(rows):
            y_pos = margin_y + (label_height * row_index)
            for col_index in range(cols):
                qr_index = row_index * cols + col_index
                if qr_index < len(page_qr_codes):
                    tile = page_qr_codes[qr_index]
                    x_pos = margin_x + (label_width * col_index)
                    tile_x = x_pos + (label_width - tile.size[0]) // 2
                    tile_y = y_pos + (label_height - tile.size[1]) // 2
                    pageTemp.paste(tile, (tile_x, tile_y))

        page_start_index = page_index * codes_per_page
        page_end_index = page_start_index + codes_per_page
        page_uuids = uuidList[page_start_index:page_end_index]
        range_start = start_index + page_start_index
        range_end = range_start + len(page_uuids) - 1
        range_pad_width = max(3, len(str(start_index + N - 1)))
        if base_name:
            file_stem = _build_output_stem(
                base_name=base_name,
                start_index=range_start,
                end_index=range_end,
                pad_width=range_pad_width
            )
        else:
            file_stem = str(page_nr)

        imgName = sanitize_path(os.path.join(outdir, f'{file_stem}.jpg'))
        pageTemp.save(imgName, 'JPEG', quality=95, DPI=(dpi, dpi))
        print(f"    Saved: {imgName}")

        pdfName = sanitize_path(os.path.join(outdir, f'{file_stem}.pdf'))
        pageTemp.save(
            pdfName,
            'PDF',
            resolution=float(dpi),
            quality=100,
            subsampling=0
        )
        print(f"    Saved: {pdfName}")

        txtName = sanitize_path(os.path.join(outdir, f'{file_stem}.txt'))
        with open(txtName, 'w') as f:
            for uid in page_uuids:
                f.write(f'{uid}\n')
        print(f"    Saved: {txtName}")

        page_nr += 1

    print(
        f"Successfully generated {N} NFC labels in "
        f"{len(page_chunks)} sheets."
    )
    print(f"Output directory: {outdir}")


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

    parser.add_argument(
        '--nfc',
        action='store_true',
        help='Generate NFC-style labels with 21mm QR, 30mm circle outline, '
             'and a 5mm blank center.'
    )

    parser.add_argument(
        '--uuid-file',
        type=str,
        help='Path to .txt file with one UUID per line. When provided, UUIDs '
             'are loaded from file instead of generated.'
    )

    parser.add_argument(
        '--name-file',
        type=str,
        help='Path to .txt file with one human-readable name per line '
             '(e.g. BEAM01). Names are printed below each QR code.'
    )

    parser.add_argument(
        '--base-name',
        type=str,
        help='Auto-generate names as <base-name>_<index>. Index is 1-based '
             'and zero-padded using the number of requested codes '
             '(e.g. 23 -> MY_COMP_01..MY_COMP_23, '
             '100 -> MY_COMP_001..MY_COMP_100).'
    )

    parser.add_argument(
        '--start-index',
        type=int,
        default=1,
        help='First index to use for auto-generated base names. '
             'Example: --base-name MY_COMP --start-index 22 with --count 23 '
             'produces MY_COMP_22..MY_COMP_44.'
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

        if args.uuid_file:
            args.uuid_file = sanitize_path(args.uuid_file)
            if not os.path.isfile(args.uuid_file):
                print(f'ERROR: UUID file not found: {args.uuid_file}',
                      file=sys.stderr)
                sys.exit(1)

        if args.name_file:
            args.name_file = sanitize_path(args.name_file)
            if not os.path.isfile(args.name_file):
                print(f'ERROR: Name file not found: {args.name_file}',
                      file=sys.stderr)
                sys.exit(1)

        if args.name_file and args.base_name:
            print(
                'ERROR: Use either --name-file or --base-name, not both.',
                file=sys.stderr
            )
            sys.exit(1)

        if args.base_name:
            args.base_name = args.base_name.strip()
            if not args.base_name:
                print('ERROR: --base-name cannot be empty.', file=sys.stderr)
                sys.exit(1)

        if args.start_index <= 0:
            print('ERROR: --start-index must be a positive integer.',
                  file=sys.stderr)
            sys.exit(1)

        # Create output directory if it doesn't exist
        output_dir = sanitize_path(args.output_dir)
        print(f"Creating output directory: {output_dir}")
        os.makedirs(output_dir, exist_ok=True)

        # Generate labels with CLI arguments
        print("Starting QR code generation...")
        if args.nfc:
            generate_nfc_labels(
                N=args.count,
                cols=args.cols,
                rows=args.rows,
                outdir=output_dir,
                uuid_file=args.uuid_file,
                name_file=args.name_file,
                base_name=args.base_name,
                start_index=args.start_index
            )
            print(f'CLI: Successfully generated {args.count} NFC QR codes in '
                  f'{output_dir}')
        else:
            generate_labels(
                N=args.count,
                cols=args.cols,
                rows=args.rows,
                outdir=output_dir,
                qr_size=args.qr_size,
                error_correction=args.error_correction,
                qr_version=args.qr_version,
                adaptive_layout=args.adaptive_layout,
                uuid_file=args.uuid_file,
                name_file=args.name_file,
                base_name=args.base_name,
                start_index=args.start_index
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
