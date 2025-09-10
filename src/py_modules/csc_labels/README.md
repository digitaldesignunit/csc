# CSC Labels - QR Code Label Generator

A Python module for generating QR code labels designed for A4 label sheets with UUID encoding. Each QR code contains a unique UUID and is formatted for printing on custom A4 label sheets (3 columns × 7 rows = 21 labels per sheet).

## Features

- Generate unique QR codes with UUID encoding
- Designed for A4 label sheets (70mm × 42mm labels)
- Configurable QR code size, error correction, and version
- Command line interface for easy batch processing
- High-quality output at 300 DPI for professional printing

## Installation

1. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. The module can be used as a Python package or run directly as a script.

## Usage

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
```

#### Command Line Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `count` | int | - | Number of QR codes to generate (required) |
| `--qr-size` | float | 0.7 | QR code size control (0.0-1.0 scale) |
| `--error-correction` | str | L | Error correction level (L/M/Q/H) |
| `--qr-version` | int | 1 | QR code version (1-40) |
| `--output-dir` | str | `./output` | Output directory for generated sheets |

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
from csc_labels import generate_labels

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
```

#### Function Parameters

- `N` (int): Number of QR codes to generate
- `cols` (int, default=3): Columns per sheet
- `rows` (int, default=7): Rows per sheet
- `outdir` (str): Output directory path
- `qr_size` (float, default=0.8): QR code size (0.0-1.0)
- `error_correction` (str, default='L'): Error correction level
- `qr_version` (int, default=1): QR code version (1-40)

## Output Format

- **File format**: JPEG images at 300 DPI
- **Page size**: A4 (210mm × 297mm)
- **Label size**: 70mm × 42mm per label
- **Layout**: 3 columns × 7 rows = 21 labels per sheet
- **Borders**: 4mm top and bottom margins
- **Naming**: Sequential page numbers (1.jpg, 2.jpg, etc.)

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
