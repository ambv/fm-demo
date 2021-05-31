from array import array
import timeit

from fm import sd, sd2


def test_py_sd():
    a = array("h", range(10000))
    func = sd.py_stddev
    assert int(func(a)) == 2886
    print(func, timeit.timeit(lambda: func(a), number=1000))


def test_py_sd2():
    a = array("h", range(10000))
    func = sd2.py_stddev
    assert int(func(a)) == 2886
    print(func, timeit.timeit(lambda: func(a), number=1000))


def test_py_sd_cy():
    a = array("h", range(10000))
    func = sd2.cy_stddev
    assert int(func(a)) == 2886
    print(func, timeit.timeit(lambda: func(a), number=1000))
