# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import time


# LOCAL MODULE IMPORTS --------------------------------------------------------

import csc_sheetscan.utilities as util


# FUNCTION DEFINITIONS --------------------------------------------------------

def test_profiler():
    p = util.Profiler()
    p.start()
    time.sleep(1)
    rs = p.rawstop()
    assert isinstance(rs, float)
    assert rs > 0
    p.start()
    time.sleep(1)
    s = p.stop()
    assert isinstance(s, float)
    assert s > 0
    p.start()
    time.sleep(1)
    assert p.results() is None
    p.stop()
    res = p.results()
    assert isinstance(res, float)
    assert res > 0
