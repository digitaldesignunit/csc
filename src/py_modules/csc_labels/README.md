# CSC Labels - QR Code Label Generator

A Python module for generating QR code labels designed for A4 label sheets with UUID encoding. Each QR code contains a unique UUID and is formatted for printing on custom A4 label sheets (3 columns × 7 rows = 21 labels per sheet).

## Features

- Generate unique QR codes with UUID encoding
- Designed for A4 label sheets (70mm × 42mm labels)
- Configurable QR code size, error correction, and version
- NFC label mode with fixed physical dimensions:
  - 21mm QR code square (default)
  - 30mm grey outlined circle (default)
  - 5mm blank center circle (default)
- Command line interface for easy batch processing
- Auto-generate human-readable names from a base name with indexed suffixes
- Continue base-name numbering from a custom first index (e.g. start at 22)
- High-quality output at 300 DPI for professional printing

## Installation

1. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. The module can be used as a Python package or run directly as a script.

## Usage

### NFC Labels

Use NFC mode to generate labels with fixed physical geometry for NFC tags.

- QR square size: 21mm (default, configurable)
- Outer circle diameter: 30mm (default, configurable)
- Center blank circle diameter: 5mm (default, configurable)
- Placement: centered in each label cell on the A4 sheet layout

Quick start:

```bash
python labels.py 21 --nfc
```

Use existing UUIDs and/or human-readable names from text files:

```bash
# Existing UUIDs only (one UUID per line)
python labels.py 21 --uuid-file ./uuids.txt

# Human-readable names only (one name per line)
python labels.py 21 --name-file ./names.txt

# Auto-generate human-readable names from a base name
# 23 codes -> MY_COMP_01 ... MY_COMP_23
python labels.py 23 --base-name MY_COMP

# 100 codes -> MY_COMP_001 ... MY_COMP_100
python labels.py 100 --base-name MY_COMP

# Continue numbering from a custom first index
# 23 codes from index 22 -> MY_COMP_22 ... MY_COMP_44
python labels.py 23 --base-name MY_COMP --start-index 22

# Both together
python labels.py 21 --uuid-file ./uuids.txt --name-file ./names.txt

# Both together in NFC mode
python labels.py 21 --nfc --uuid-file ./uuids.txt --name-file ./names.txt

# Base name generation in NFC mode
python labels.py 23 --nfc --base-name MY_COMP
```

Python API:

```python
from csc_labels import generate_nfc_labels

generate_nfc_labels(21)
```

### Command Line Interface

The module provides a command line interface for easy batch processing:

```bash
python labels.py <count> [options]
```

#### Basic Usage

```bash
# Generate 21 QR codes with default settings (1 full sheet)
python labels.py 21

# Generate 42 QR codes (2 full sheets)
python labels.py 42
```

#### Advanced Usage

```bash
# Generate with custom QR code size
python labels.py 21 --qr-size 0.8

# Generate with high error correction
python labels.py 21 --error-correction H

# Generate with higher QR version for more complex codes
python labels.py 21 --qr-version 2

# Generate to custom output directory
python labels.py 21 --output-dir /path/to/output

# Combine multiple options
python labels.py 42 --qr-size 0.8 --error-correction H --qr-version 2 --output-dir ./custom_output

# Generate NFC-style labels
python labels.py 21 --nfc

# Generate labels with auto-generated names
python labels.py 23 --base-name MY_COMP

# Continue generated names from index 22
python labels.py 23 --base-name MY_COMP --start-index 22
```

#### Command Line Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `count` | int | - | Number of QR codes to generate (required) |
| `--qr-size` | float | 0.7 | QR code size control (0.0-1.0 scale) |
| `--error-correction` | str | L | Error correction level (L/M/Q/H) |
| `--qr-version` | int | 1 | QR code version (1-40) |
| `--output-dir` | str | `./output` | Output directory for generated sheets |
| `--nfc` | flag | false | Generate NFC-style labels (21mm QR, 30mm circle, 5mm blank center) |
| `--uuid-file` | str | - | Path to `.txt` file with one UUID per line |
| `--name-file` | str | - | Path to `.txt` file with one human-readable name per line |
| `--base-name` | str | - | Auto-generate names as `<base-name>_<index>` with 1-based zero-padded index |
| `--start-index` | int | 1 | First index for auto-generated base names (used with `--base-name`) |

`--name-file` and `--base-name` are mutually exclusive.

#### Error Correction Levels

- **L (Low)**: ~7% error correction - simplest QR codes
- **M (Medium)**: ~15% error correction - balanced
- **Q (Quartile)**: ~25% error correction - more robust
- **H (High)**: ~30% error correction - most robust

#### QR Code Versions

- **Version 1**: 21×21 modules - simplest, smallest data capacity
- **Version 2**: 25×25 modules - slightly more complex
- **Higher versions**: More modules, higher data capacity

### Python API

You can also use the module programmatically:

```python
from csc_labels import generate_labels, generate_nfc_labels

# Generate 21 QR codes with default settings
generate_labels(21)

# Generate with custom settings
generate_labels(
    N=42,
    qr_size=0.8,
    error_correction='H',
    qr_version=2,
    outdir='/path/to/output'
)

# Generate NFC labels with defaults:
# qr_size_mm=21.0, outer_circle_mm=30.0, center_blank_mm=5.0
generate_nfc_labels(21)

# Generate NFC labels with custom dimensions
generate_nfc_labels(
    21,
    qr_size_mm=20.0,
    outer_circle_mm=28.0,
    center_blank_mm=4.0
)

# Standard labels from existing UUIDs and names
generate_labels(
    21,
    uuid_file='./uuids.txt',
    name_file='./names.txt'
)

# Standard labels with auto-generated names:
# 23 codes -> MY_COMP_01 ... MY_COMP_23
generate_labels(
    23,
    base_name='MY_COMP'
)

# Continue generated names from a custom first index
generate_labels(
    23,
    base_name='MY_COMP',
    start_index=22
)

# NFC labels from existing UUIDs and names
generate_nfc_labels(
    21,
    uuid_file='./uuids.txt',
    name_file='./names.txt'
)

# NFC labels with auto-generated names
generate_nfc_labels(
    100,
    base_name='MY_COMP'
)
```

#### Function Parameters

- `N` (int): Number of QR codes to generate
- `cols` (int, default=3): Columns per sheet
- `rows` (int, default=7): Rows per sheet
- `outdir` (str): Output directory path
- `qr_size` (float, default=0.8): QR code size (0.0-1.0)
- `error_correction` (str, default='L'): Error correction level
- `qr_version` (int, default=1): QR code version (1-40)
- `uuid_file` (str, optional): `.txt` file with one UUID per line
- `name_file` (str, optional): `.txt` file with one human-readable name per line
- `base_name` (str, optional): Auto-generate names as
  `<base_name>_<index>`, where index starts at `start_index` and is
  zero-padded to `max(2, len(str(start_index + N - 1)))`
- `start_index` (int, default=1): First index used for auto-generated names

`generate_nfc_labels(...)` parameters:

- `N` (int): Number of QR codes to generate
- `cols` (int, default=3): Columns per sheet
- `rows` (int, default=7): Rows per sheet
- `outdir` (str): Output directory path
- `qr_size_mm` (float, default=21.0): Printed QR square size in mm
- `outer_circle_mm` (float, default=30.0): Printed outer circle diameter in mm
- `center_blank_mm` (float, default=5.0): Blank center circle diameter in mm

## Output Format

- **File format**: JPEG images at 300 DPI
- **Page size**: A4 (210mm × 297mm)
- **Label size**: 70mm × 42mm per label
- **Layout**: 3 columns × 7 rows = 21 labels per sheet
- **Borders**: 4mm top and bottom margins
- **Naming without base name**: Sequential page numbers (`1.jpg`, `2.jpg`, etc.)
- **Naming with base name**: Date + base + index range, for all output files
  (`YYMMDD_BASE_001-021.jpg/.pdf/.txt`, e.g. `260422_AGGREGATIONS_001-021.pdf`)

## Examples

### Simple QR Codes
```bash
python labels.py 21 --qr-size 0.33 --error-correction L --qr-version 1
```

### Standard QR Codes
```bash
python labels.py 21 --qr-size 0.5 --error-correction M --qr-version 1
```

### Complex QR Codes
```bash
python labels.py 21 --qr-size 0.8 --error-correction H --qr-version 2
```

## Requirements

- Python 3.6+
- numpy >= 1.15.4
- pillow
- qrcode

## License

See the main project license file.

## Contributing

Please follow the project's coding standards and submit pull requests for any improvements.
