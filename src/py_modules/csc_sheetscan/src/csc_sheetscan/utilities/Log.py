# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import sys


# CLASS DEFINITION ------------------------------------------------------------

class Log(object):
    def __init__(self, out=sys.stdout, err=sys.stderr):
        self.out = out
        self.err = err

    def flush(self):
        self.out.flush()
        self.err.flush()

    def write(self, message, end='\n'):
        self.flush()
        self.out.write(f'{message}{end}')
        self.out.flush()

    def info(self, message, end='\n'):
        self.write(f'[INFO] {message}', end=end)

    def warn(self, message, end='\n'):
        self.write(f'[WARNING] {message}', end=end)

    def error(self, message, end='\n'):
        self.write(f'[ERROR] {message}', end=end)

    def opencv(self, message, end='\n'):
        self.write(f'[OPENCV] {message}', end=end)

    def qreader(self, message, end='\n'):
        self.write(f'[QREADER] {message}', end=end)
