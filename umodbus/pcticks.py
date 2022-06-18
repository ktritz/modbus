from time import perf_counter_ns


def ticks_ms():
    return perf_counter_ns() // 1_000_000


def ticks_diff(ticks1, ticks2):
    return ticks1 - ticks2

