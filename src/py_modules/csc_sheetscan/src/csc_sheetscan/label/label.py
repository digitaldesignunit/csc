# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import glob
import math
import os
import uuid

# ADDITIONAL MODULE IMPORTS ---------------------------------------------------

import qrcode
from PIL import Image, ImageDraw, ImageFont

# LOCAL MODULE IMPORTS --------------------------------------------------------

from csc_sheetscan.utilities import sanitize_path


# ENVIRONMENT VARIABLES -------------------------------------------------------

# directory of this particular file
_HERE = os.path.dirname(sanitize_path(__file__))

# retrieve fontsdir
_FONTSDIR = sanitize_path(os.path.join(_HERE, 'fonts'))

# retrieve qrdir
_OUTPUTDIR = sanitize_path(os.path.join(_HERE, 'output'))


# FUNCTION DEFINITIONS --------------------------------------------------------

def _divide_chunks(seq: list, n: int):
    """
    Yield successive n-sized chunks from l.
    """
    # looping till length l
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def gen_labels(N: int,
               cols: int = 3,
               rows: int = 7,
               prefix: str = 'A',
               outdir: str = _OUTPUTDIR,
               fontsdir: str = _FONTSDIR):
    """
    Create N amount of unique QR-Codes with UUID and Name displayed next to it.

    Parameters
    ----------
    N : int
        Number or QR-Codes to generate. Should be a multiple of (cols * rows).
    cols : int
        Columns of the output sheet of QR-Codes.
    rows: int
        Rows of the output sheet of QR-Codes.
    prefix: str
        Prefix for human-readable names.


    Returns
    -------
    True if uuid_to_test is a valid UUID, otherwise False

    Notes
    -------
    N should be a multiple of (rows * cols)
    """

    qrCodeList = []
    for i in range(0, N):
        nameTemp = '{0}_{1:0>3}'.format(prefix, i)
        uuidTemp = uuid.uuid4()
        # QRCode class
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )

        # use if Name and UUID should be included in QR-Code
        # qrData = uuidTemp, nameTemp
        # qr.add_data(qrData)

        # use if only theUUID should be included in QR-Code
        qr.add_data(uuidTemp)
        qr.make(fit=True)

        img = qr.make_image(fill_color='black', back_color='white')

        # get dimensions of QR-Code image
        widthA, heightA = img.size

        # create a new image
        textImg = Image.new('RGB',
                            (math.floor(((widthA * 5) / 3) - 6), heightA),
                            (255, 255, 255))

        # get the fonts
        tt_bold = sanitize_path(os.path.join(fontsdir,
                                             'TitilliumWeb-Bold.ttf'))
        fnt = ImageFont.truetype(tt_bold, 40)

        tt_light = sanitize_path(os.path.join(fontsdir,
                                              'TitilliumWeb-Light.ttf'))
        fnt2 = ImageFont.truetype(tt_light, 35)

        # get a drawing context
        d = ImageDraw.Draw(textImg)

        # make UUID multiline
        stringUidTemp = str(uuidTemp)
        stringUidTemp = stringUidTemp.split('-')
        stringUidTemp = '\n'.join(stringUidTemp)

        # draw multiline text
        d.multiline_text((widthA, round(heightA/10)),
                         f'{nameTemp}',
                         font=fnt,
                         fill=(0))
        d.multiline_text((widthA, round(heightA/10)+60),
                         f'{stringUidTemp}',
                         font=fnt2,
                         fill=(0))

        # paste QR-Code to the 0,0 coordinate
        textImg.paste(img, box=(0, 0), mask=None)
        qrCodeList.append(textImg)

        # get dimensions of complete tag image
        widthB, heightB = textImg.size

        # define image name and save to folder
        # use to export single QR codes
        # imgName = 'C:\QR Codes\{}.png'
        # textImg.save(imgName.format(uuidTemp))

        # use if UUIDs and names need to be used a a list
        # UUID.append(uuidTemp)
        # names.append(nameTemp)

    # How many columns the sheet should have
    qrCodeListChunks = list(_divide_chunks(qrCodeList, cols))

    lineImg = []
    for Chunk in qrCodeListChunks:
        # create a new image
        lineImgTemp = Image.new('RGB',
                                (math.floor(widthB * 3), heightB),
                                (255, 255, 255))
        # paste QR-Codes to the new picture next to eachother
        indexA = 0
        for c in Chunk:
            lineImgTemp.paste(c, box=(widthB * indexA, 0), mask=None)
            indexA = indexA+1
        lineImg.append(lineImgTemp)

    # How many rows each list should have
    lineImgChunks = list(_divide_chunks(lineImg, rows))

    # List for numbering the exported pages
    existing_pages = glob.glob(os.path.join(outdir, "*.jpg"))
    page_nr = len(existing_pages) + 1

    indexB = 0
    for lines in lineImgChunks:
        # create a new image
        pageTemp = Image.new('RGB',
                             (math.floor(widthB * 3), heightB * 7),
                             (255, 255, 255))
        # paste QR-Codes to the new picture below eachother
        indexB = 0
        for ln in lines:
            pageTemp.paste(ln, box=(0, (heightB*indexB)), mask=None)
            indexB += 1
        # save the image using the pagenumber
        imgName = sanitize_path(os.path.join(outdir, f'{page_nr}.jpg'))
        pageTemp.save(imgName)
        page_nr += 1


# MAIN ROUTINE ----------------------------------------------------------------

if __name__ == '__main__':
    gen_labels(105)
