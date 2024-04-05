#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import base64
import io
import os


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

import matplotlib.pyplot as plt


# FUNCTION DEFINITIONS --------------------------------------------------------

def sanitize_path(fp: str = '') -> str:
    """Sanitizes a filepath an returns the result."""
    return os.path.abspath(os.path.realpath(os.path.normpath(fp)))


def mm_to_inches(mm):
    """Convert millimeters to inches."""
    return mm / 25.4


def plot_polyline_to_html(coordinates,
                          name='Polyline from Coordinates',
                          image_width_mm=1500,
                          image_height_mm=1500,
                          scalefactor=0.1,
                          pixel_width=350):
    """
    Plot a polyline based on a list of [x, y] coordinates and returns HTML
    markup displaying the generated image. Image dimensions are specified in
    millimeters and can be resized to a specific pixel width.

    Args:
    - coordinates (list of lists): A list where each element is a list of
      [x, y] coordinates.
    - image_width_mm (int, optional): Width of the output image in millimeters.
      Defaults to 200.
    - image_height_mm (int, optional): Height of the output image in
      millimeters. Defaults to 100.
    - pixel_width (int, optional): Desired width of the output image in pixels
      for resizing.

    Returns:
    - A string containing HTML markup for displaying the generated image.
    """
    # Convert mm dimensions to inches for matplotlib
    image_width_in = mm_to_inches(image_width_mm * scalefactor)
    image_height_in = mm_to_inches(image_height_mm * scalefactor)

    # If pixel_width is specified, calculate DPI to maintain the desired width
    dpi = 96  # Default DPI
    if pixel_width is not None:
        dpi = pixel_width / image_width_in

    coordinates = [[c[0] * scalefactor, c[1] * scalefactor]
                   for c in coordinates]

    # Create the figure with the specified dimensions
    fig, ax = plt.subplots(figsize=(image_width_in, image_height_in), dpi=dpi)
    x_values, y_values = zip(*coordinates)
    ax.plot(x_values, y_values, marker='o')
    ax.set_title(name)
    ax.set_xlabel('X Coordinate')
    ax.set_ylabel('Y Coordinate')

    # Save the plot to a bytes buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)  # Close the figure to free up memory

    # Encode the buffer to Base64 and decode to UTF-8 for HTML embedding
    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    html = f'<img src="data:image/png;base64,{img_base64}"/>'

    return html
