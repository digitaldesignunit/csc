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
def gource(c, mode='overview', output_dir='viz'):
    """
    Create gource video in specified output directory.

    Args:
        mode: Either 'overview' or 'track' (default: 'overview')
        output_dir: Output directory for the video (default: 'viz')
    """
    if mode not in ['overview', 'track']:
        raise ValueError("Mode must be either 'overview' or 'track'")

    repodir = os.path.normpath(os.path.dirname(__file__))
    with chdir(repodir):
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Gource visualization
        try:
            print(f"Creating gource {mode} visualization...")

            if mode == 'overview':
                gource_cmd = (
                    "gource {0} -1920x1080 -f --multi-sampling -a 1 "
                    "-s 1 --hide bloom,mouse,progress --camera-mode "
                    "overview -r 60 -o {1}/{2}.ppm"
                ).format(repodir, output_dir, mode)
                c.run(gource_cmd)
            else:  # track mode
                gource_cmd = (
                    "gource {0} -1920x1080 -f --multi-sampling -a 1 "
                    "-s 1 --hide bloom,mouse,progress --camera-mode "
                    "track -r 60 -o {1}/{2}.ppm"
                ).format(repodir, output_dir, mode)
                c.run(gource_cmd)
        except exceptions.UnexpectedExit:
            print("Gource is not installed or not in the current PATH! "
                  "See https://gource.io/ for info on installation.")
            return

        # FFmpeg conversion
        try:
            print("Converting using FFMPEG...")
            ffmpeg_cmd = (
                "ffmpeg -y -r 60 -f image2pipe -vcodec ppm -i "
                "{0}/{1}.ppm -vcodec libx264 -preset medium "
                "-pix_fmt yuv420p -crf 1 -threads 0 -bf 0 "
                "{0}/{1}.mp4"
            ).format(output_dir, mode)
            c.run(ffmpeg_cmd)
            os.remove(f"{output_dir}/{mode}.ppm")
            print(f"Video saved to {output_dir}/{mode}.mp4")
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
