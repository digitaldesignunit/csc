# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import contextlib
import os


# ADDITIONAL MODULE IMPORTS ---------------------------------------------------

from invoke import task, exceptions


# LOCAL MODULE IMPORTS --------------------------------------------------------

import csc_sheetscan


# LOGGING ---------------------------------------------------------------------

log = csc_sheetscan.utilities.Log()


# TASK DEFINITIONS ------------------------------------------------------------

@task(default=True)
def help(c):
    """
    Lists all available tasks and info on their usage.
    """
    c.run("invoke --list")
    log.info("Use \"invoke -h <taskname>\" to get detailed help for a task.")


@task()
def lint(c):
    """
    Check the coding style using flake8 python linter.
    """
    with chdir(csc_sheetscan.REPODIR):
        log.info("Running flake8 python linter on source folder...")
        c.run("flake8 --statistics src")


@task()
def check(c):
    """
    Perform various checks such as linting, etc.
    """
    with chdir(csc_sheetscan.REPODIR):
        lint(c)
        log.info("All checks passed.")


@task(help={
    "checks": ("Set to True to run all checks before running tests. "
               "Defaults to False")})
def test(c, checks=False):
    """
    Run all tests.
    """
    if checks:
        check(c)

    log.info("Running all tests...")
    with chdir(csc_sheetscan.TESTDIR):
        c.run("coverage run -m pytest")
        log.info("Analyzing coverage....")
        c.run("coverage report -m")


@task()
def gource(c):
    """
    Create gource video in /viz folder.
    """
    repodir = csc_sheetscan.REPODIR
    with chdir(repodir):
        vizpath = os.path.join(repodir, "viz")
        if not os.path.exists(vizpath):
            os.makedirs(vizpath)

        # Gource visualization
        try:
            # overview
            log.info("Creating gource overview visualization...")
            c.run(("gource {0} -1920x1080 -f --multi-sampling -a 1 -s 1 "
                   "--hide bloom,mouse,progress --camera-mode overview -r 60 "
                   "-o viz/overview.ppm").format(repodir))
            # track
            log.info("Creating gource track visualization...")
            c.run(("gource {0} -1920x1080 -f --multi-sampling -a 1 -s 1 "
                   "--hide bloom,mouse,progress --camera-mode track -r 60 -o "
                   "viz/track.ppm").format(repodir))
        except exceptions.UnexpectedExit:
            log.warn("Gource is not installed or not in the current PATH! "
                     "See https://gource.io/ for info on installation.")

        # FFmpeg conversion
        try:
            log.info("Converting using FFMPEG...")
            c.run("ffmpeg -y -r 60 -f image2pipe -vcodec ppm -i "
                  "viz/overview.ppm -vcodec libx264 -preset medium "
                  "-pix_fmt yuv420p -crf 1 -threads 0 -bf 0 viz/overview.mp4")
            os.remove("viz/overview.ppm")
            c.run("ffmpeg -y -r 60 -f image2pipe -vcodec ppm -i "
                  "viz/track.ppm -vcodec libx264 -preset medium "
                  "-pix_fmt yuv420p -crf 1 -threads 0 -bf 0 viz/track.mp4")
            os.remove("viz/track.ppm")
        except exceptions.UnexpectedExit:
            log.warn("FFmpeg is not installed or not in the current PATH! "
                     "See https://ffmpeg.org/ for info on installation.")


@task(help={
    "indir": "Directory with the chessboard images for calibration.",
    "coeffs": "File where the camera coefficients should be stored."})
def imgcalibration(c,
                   indir=csc_sheetscan.sheets._CHESSBOARD_DIR,
                   coeffs=csc_sheetscan.sheets._COEFF_FILE):
    """
    Run image camera calibration routine from sheets module
    """
    with chdir(csc_sheetscan.IMGDIR):
        log.info("Running camera calibration routine...")
        csc_sheetscan.sheets.compute_camera_coefficients(
                                    chessboard_dir=indir,
                                    coeff_file=coeffs)


@task(help={
    "indir": "Directory with the input raw images before undistortion.",
    "outdir": "Directory where the undistorted images should be saved.",
    "coeffs": "File where the camera coefficients are stored."})
def imgundistortion(c,
                    indir=csc_sheetscan.sheets._RAW_DIR,
                    outdir=csc_sheetscan.sheets._UNDIST_DIR,
                    coeffs=csc_sheetscan.sheets._COEFF_FILE):
    """
    Run image undistortion routine from sheets module.
    """
    with chdir(csc_sheetscan.IMGDIR):
        log.info("Running undistortion routine...")
        csc_sheetscan.sheets.undistort_image_files(
            indir=indir,
            outdir=outdir,
            coeff_file=coeffs
        )


@task(help={
    "width": "Width of the working area.",
    "height": "Height of the working area.",
    "img": ("Undistorted sample image to use for computing the perspective "
            "transformation."),
    "xform": "File where the perspective transformation should be saved."})
def imgperspective(c,
                   width: int = 1500,
                   height: int = 1500,
                   img: str = csc_sheetscan.sheets._XFORM_IMG,
                   xform: str = csc_sheetscan.sheets._XFORM_FILE):
    """
    Run image perspective calibration and save transformation matrix to file.
    """
    with chdir(csc_sheetscan.IMGDIR):
        log.info("Running camera perspective calibration routine...")
        log.info("Width: {0} // Height: {1}".format(width, height))
        csc_sheetscan.sheets.compute_perspective_xform(
            img_file=img,
            xform_file=xform,
            width=width,
            height=height
        )


@task(help={
    "queuedir": "Directory with the chessboard images for calibration.",
    "datasetsdir": "Directory with the input raw images before undistortion.",
    "outdir": "Directory where the final .json files will be saved.",
    "archivedir": "Directory where the comüiled processed archive is saved.",
    "name": "Directory where the undistorted images should be saved.",
    "width": "Width of the working area.",
    "height": "Height of the working area.",
    "thickness": "Material thickness of the scanned sheets. Defaults to 12.0",
    "bthresh": "Binary threshold for contour detection.",
    "athresh": "Area threshold for contour detection.",
    "chain": "Chain approximation flag for contour detection.",
    "eps": "Epsilon value for contour approximation.",
    "invert": "Boolean flag to invert image before contour detection.",
    "external": "Boolean to only yield outer contours.",
    "largestonly": "Boolean to only yield largest contour.",
    "qrcrop": "Value to center-crop images before QR Code detection.",
    "preprocess": "Boolean flag for preprocessing.",
    "showcrop": "Boolean flag to display qr-cropped image for debugging.",
    "showresult": "Boolean flag to display detection results for debug.",
    "archive": "If True, will archive dataset as .zip."})
def processqueue(c,
                 queuedir: str = csc_sheetscan.sheets._QUEUE_DIR,
                 datasetsdir: str = csc_sheetscan.sheets._DATASETS_DIR,
                 outdir: str = csc_sheetscan.sheets._SHEETS_DIR,
                 archivedir: str = csc_sheetscan.sheets._PROCESSED_DIR,
                 name: str = csc_sheetscan.sheets._DEFAULTNAME,
                 width: int = 1500,
                 height: int = 1500,
                 thickness: float = 12.0,
                 bthresh: int = -1,
                 athresh: float = 10000.0,
                 chain: int = 0,
                 eps: float = 0.00025,
                 invert: bool = False,
                 external: bool = True,
                 largestonly: bool = True,
                 qrcrop: int = 1500,
                 preprocess: bool = False,
                 showcrop: bool = False,
                 showresult: bool = False,
                 archive: bool = True):
    """
    Process all elements in the queue.
    """
    with chdir(csc_sheetscan.IMGDIR):
        # PREPARATION ROUTINE -------------------------------------------------
        log.info('Running preparation routine and creating folders...')
        (main_path,
         chess_path,
         raw_path,
         undist_path,
         coeff_file,
         xform_file) = csc_sheetscan.sheets.prepare_dataset(
                                                queuedir=queuedir,
                                                datasetsdir=datasetsdir,
                                                name=name)

        # PREPROCESSING IMAGES ------------------------------------------------
        if preprocess:
            log.info('Running preprocessing routine...')
            # preprocess chessboard imgs
            csc_sheetscan.sheets.preprocess_image_files(indir=chess_path)
            # preprocess raw imgs
            csc_sheetscan.sheets.preprocess_image_files(indir=raw_path)

        # CAMERA CALIBRATION (CHESSBOARD) -------------------------------------
        log.info('Running camera calibration routine...')
        csc_sheetscan.sheets.compute_camera_coefficients(
                                        chessboard_dir=chess_path,
                                        coeff_file=coeff_file)

        # UNDISTORTION --------------------------------------------------------
        log.info('Running undistortion routine...')
        csc_sheetscan.sheets.undistort_image_files(
            indir=raw_path,
            outdir=undist_path,
            coeff_file=coeff_file
        )

        # FIND XFORM IMAGE ----------------------------------------------------
        xform_img = csc_sheetscan.sheets.find_xform_img(undist_path)

        # RUN PERSPECTIVE WARP ------------------------------------------------
        log.info('Running camera perspective calibration routine...')
        log.info('Width: {0} // Height: {1}'.format(width, height))
        csc_sheetscan.sheets.compute_perspective_xform(
            img_file=xform_img,
            xform_file=xform_file,
            width=width,
            height=height
        )

        # CONTOUR AND QR DETECTION --------------------------------------------
        log.info('Running contour and qr code detection routine...')
        sheets = csc_sheetscan.sheets.detect_contours_and_ids( # NOQA
                                                dirpath=undist_path,
                                                xformfile=xform_file,
                                                bthresh=bthresh,
                                                athresh=athresh,
                                                width=width,
                                                height=height,
                                                thickness=thickness,
                                                chain=chain,
                                                eps=eps,
                                                invert=invert,
                                                external=external,
                                                largestonly=largestonly,
                                                qrcrop=qrcrop,
                                                showcrop=showcrop,
                                                showresult=showresult)

        # SAVE TO FILES -------------------------------------------------------
        log.info('Saving scanned sheets to JSON files...')
        csc_sheetscan.sheets.save_sheets_to_json(
            sheets=sheets,
            dirpath=outdir
        )

        # DO SOME HOUSEKEEPING ------------------------------------------------
        if archive:
            log.info('Archiving scanned dataset...')
            csc_sheetscan.sheets.save_dataset_to_archive(
                rootdir=main_path,
                outdir=archivedir
            )
        else:
            log.info('No archiving of datasets due to archive=False!')


@task(help={
    "datasetsdir": "Directory with the input raw images before undistortion.",
    "outdir": "Directory where the final .json files will be saved.",
    "width": "Width of the working area.",
    "height": "Height of the working area.",
    "thickness": "Material thickness of the scanned sheets. Defaults to 12.0",
    "bthresh": "Binary threshold for contour detection.",
    "athresh": "Area threshold for contour detection.",
    "chain": "Chain approximation flag for contour detection.",
    "eps": "Epsilon value for contour approximation.",
    "invert": "Boolean flag to invert image before contour detection.",
    "external": "Boolean to only yield outer contours.",
    "largestonly": "Boolean to only yield largest contour.",
    "qrcrop": "Value to center-crop images before QR Code detection.",
    "showcrop": "Boolean flag to display qr-cropped image for debugging.",
    "showresult": "Boolean flag to display detection results for debug."})
def reprocessdatasets(c,
                      datasetsdir: str = csc_sheetscan.sheets._DATASETS_DIR,
                      outdir: str = csc_sheetscan.sheets._SHEETS_DIR,
                      width: int = 1500,
                      height: int = 1500,
                      thickness: float = 12.0,
                      bthresh: int = -1,
                      athresh: float = 20000.0,
                      chain: int = 0,
                      eps: float = 0.00025,
                      invert: bool = False,
                      external: bool = True,
                      largestonly: bool = True,
                      qrcrop: int = 1500,
                      showcrop: bool = False,
                      showresult: bool = False):
    """
    Re-Process all compiled datasets
    """
    with chdir(csc_sheetscan.IMGDIR):
        # LOOP OVER ALL DATASETS ----------------------------------------------
        log.info('Getting all datasets...')
        for ds in csc_sheetscan.sheets.get_all_input_datasets(fp=datasetsdir):
            # load a single dataset
            log.info(f'Loading dataset {ds} ...')
            (main_path,
             chess_path,
             raw_path,
             undist_path,
             coeff_file,
             xform_file,
             chess_imgs,
             raw_imgs,
             undist_imgs) = csc_sheetscan.sheets.load_input_dataset(ds)

            # CONTOUR AND QR DETECTION ----------------------------------------
            log.info('Running contour and qr code detection routine...')
            sheets = csc_sheetscan.sheets.detect_contours_and_ids(
                                                    dirpath=undist_path,
                                                    xformfile=xform_file,
                                                    bthresh=bthresh,
                                                    athresh=athresh,
                                                    width=width,
                                                    height=height,
                                                    thickness=thickness,
                                                    chain=chain,
                                                    eps=eps,
                                                    invert=invert,
                                                    external=external,
                                                    largestonly=largestonly,
                                                    qrcrop=qrcrop,
                                                    showcrop=showcrop,
                                                    showresult=showresult)
            # SAVE TO FILES ---------------------------------------------------
            log.info('Saving scanned sheets to JSON files...')
            csc_sheetscan.sheets.save_sheets_to_json(
                sheets=sheets,
                dirpath=outdir
            )


@task(help={
    "outdir": "Directory where the undistorted images should be saved.",
    "xform": "File where the perspective transformation should be saved.",
    "width": "Width of the working area.",
    "height": "Height of the working area.",
    "bthresh": "Binary threshold for contour detection.",
    "athresh": "Area threshold for contour detection.",
    "chain": "Chain approximation flag for contour detection.",
    "eps": "Epsilon value for contour approximation.",
    "invert": "Boolean flag to invert image before contour detection.",
    "external": "Boolean to only yield outer contours.",
    "largestonly": "Boolean to only yield largest contour.",
    "qrcrop": "Value to center-crop images before QR Code detection.",
    "showcrop": "Boolean flag to display qr-cropped image for debugging.",
    "showresult": "Boolean flag to display detection results for debug."})
def rescan(c,
           outdir: str = csc_sheetscan.sheets._UNDIST_DIR,
           xform: str = csc_sheetscan.sheets._XFORM_FILE,
           width: int = 1500,
           height: int = 1500,
           bthresh: int = -1,
           athresh: float = 20000.0,
           chain: int = 0,
           eps: float = 0.00025,
           invert: bool = False,
           external: bool = True,
           largestonly: bool = True,
           qrcrop: int = 1500,
           showcrop: bool = False,
           showresult: bool = False):
    """
    Re-run the sheet scanning process (qr and contour detection).
    """
    with chdir(csc_sheetscan.IMGDIR):
        log.info("Re-Running contour and qr code detection routine...")
        sheets = csc_sheetscan.sheets.detect_contours_and_ids( # NOQA
                                                    dirpath=outdir,
                                                    xformfile=xform,
                                                    bthresh=bthresh,
                                                    athresh=athresh,
                                                    width=width,
                                                    height=height,
                                                    chain=chain,
                                                    eps=eps,
                                                    invert=invert,
                                                    external=external,
                                                    largestonly=largestonly,
                                                    qrcrop=qrcrop,
                                                    showcrop=showcrop,
                                                    showresult=showresult)


@task(help={
    'n': 'Number of Qr-Codes to generate.',
    'cols': 'Number of columns for the sheet of QR-Codes.',
    'rows': 'Number of rows for the sheet of QR-Codes.',
    'prefix': 'Prefix for human-readable name/id.',
    'outdir': 'Folder where to save the generated sheets with QR-Codes.',
    'fontsdir': 'Folder to look for the fonts used in QR-Code generation.'})
def labels(c,
           n=105,
           cols=3,
           rows=7,
           prefix='A',
           outdir=csc_sheetscan.label._OUTPUTDIR,
           fontsdir=csc_sheetscan.label._FONTSDIR):
    """
    Run QR-Code generation.
    """
    with chdir(csc_sheetscan.IMGDIR):
        log.info('Running QR-Code generation routine...')
        csc_sheetscan.label.gen_labels(
            N=n,
            cols=cols,
            rows=rows,
            prefix=prefix,
            outdir=outdir,
            fontsdir=fontsdir
        )


# CONTEXT ---------------------------------------------------------------------

@contextlib.contextmanager
def chdir(dirname=None):
    current_dir = os.getcwd()
    try:
        if dirname is not None:
            os.chdir(dirname)
        yield
    finally:
        os.chdir(current_dir)
