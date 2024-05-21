# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import contextlib
import os


# ADDITIONAL MODULE IMPORTS ---------------------------------------------------

from invoke import task, exceptions


# TASK DEFINITIONS ------------------------------------------------------------

@task(default=True)
def help(c):
    """
    Lists all available tasks and info on their usage.
    """
    c.run("invoke --list")
    print("Use \"invoke -h <taskname>\" to get detailed help for a task.")


@task()
def gource(c):
    """
    Create gource video in /viz folder.
    """
    repodir = os.path.normpath(os.path.dirname(__file__))
    with chdir(repodir):
        vizpath = os.path.join(repodir, "viz")
        if not os.path.exists(vizpath):
            os.makedirs(vizpath)

        # Gource visualization
        try:
            # overview
            print("Creating gource overview visualization...")
            c.run(("gource {0} -1920x1080 -f --multi-sampling -a 1 -s 1 "
                   "--hide bloom,mouse,progress --camera-mode overview -r 60 "
                   "-o viz/overview.ppm").format(repodir))
            # track
            print("Creating gource track visualization...")
            c.run(("gource s{0} -1920x1080 -f --multi-sampling -a 1 -s 1 "
                   "--hide bloom,mouse,progress --camera-mode track -r 60 -o "
                   "viz/track.ppm").format(repodir))
        except exceptions.UnexpectedExit:
            print("Gource is not installed or not in the current PATH! "
                  "See https://gource.io/ for info on installation.")

        # FFmpeg conversion
        try:
            print("Converting using FFMPEG...")
            c.run("ffmpeg -y -r 60 -f image2pipe -vcodec ppm -i "
                  "viz/overview.ppm -vcodec libx264 -preset medium "
                  "-pix_fmt yuv420p -crf 1 -threads 0 -bf 0 viz/overview.mp4")
            os.remove("viz/overview.ppm")
            c.run("ffmpeg -y -r 60 -f image2pipe -vcodec ppm -i "
                  "viz/track.ppm -vcodec libx264 -preset medium "
                  "-pix_fmt yuv420p -crf 1 -threads 0 -bf 0 viz/track.mp4")
            os.remove("viz/track.ppm")
        except exceptions.UnexpectedExit:
            print("FFmpeg is not installed or not in the current PATH! "
                  "See https://ffmpeg.org/ for info on installation.")


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
