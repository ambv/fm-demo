import math
from cpython cimport array
import array

cdef extern from "math.h":
    double sqrt(double m)


def py_stddev(a):
    mean = sum(a) / len(a)
    return math.sqrt((sum(((x - mean) ** 2 for x in a)) / len(a)))


def cy_stddev(array.array a):
    cdef Py_ssize_t i
    cdef Py_ssize_t n = len(a)
    cdef double m = 0.0
    cdef short *raw = a.data.as_shorts
    for i in range(n):
        m += raw[i]
    m /= n
    cdef double v = 0.0
    for i in range(n):
        v += (raw[i] - m)**2
    return sqrt(v / n)
