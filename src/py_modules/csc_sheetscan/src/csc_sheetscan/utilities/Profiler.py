# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import time


# CLASS DEFINITION ------------------------------------------------------------

class Profiler(object):
    """
    A very simple profiler
    """

    def __init__(self):
        self.start_time = None
        self.stop_time = None

    def start(self):
        """
        Start the timer and save the start time.
        """
        self.stop_time = None
        self.start_time = time.time()

    def stop(self):
        """
        Stop the timer, print and return elapsed time.
        """
        elapsed = time.time() - self.start_time
        self.stop_time = elapsed
        elapsed_ms = elapsed * 1000
        print('Elapsed Time:')
        print(str(round(elapsed, 3)) + ' s')
        print(str(round(elapsed_ms, 3)) + ' ms')
        return elapsed_ms

    def rawstop(self):
        """
        Stop the timer raw and don't print the results
        """
        elapsed = time.time() - self.start_time
        self.stop_time = elapsed
        elapsed_ms = elapsed * 1000
        return elapsed_ms

    def results(self):
        """
        Print the latest timing results
        """
        if self.stop_time is None:
            print('Timer is still running! Call stop() method first.')
            return None
        print('Elapsed Time:')
        print(str(round(self.stop_time, 3)) + ' s')
        print(str(round(self.stop_time * 1000, 3)) + ' ms')
        return self.stop_time * 1000
