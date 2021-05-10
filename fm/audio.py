from __future__ import annotations
from typing import *

from array import array
import math

import miniaudio


if TYPE_CHECKING:
    Audio = Generator[array[int], int, None]


INT16_MAX = 2 ** 15 - 1


def sine_array(sample_count: int) -> array[int]:
    numbers = []
    for i in range(sample_count):
        current = round(INT16_MAX * math.sin(i / sample_count * math.tau))
        numbers.append(current)
    return array("h", numbers)


def endless_sine(sample_count: int) -> Audio:
    sine = sine_array(sample_count)
    result = array("h")
    want_frames = yield result
    i = 0
    while True:
        result = array("h")
        left = want_frames
        while left:
            left = want_frames - len(result)
            result.extend(sine[i : i + left])
            i += left
            if i > sample_count - 1:
                i = 0
        want_frames = yield result


def get_miniaudio_playback_device(name: str) -> miniaudio.PlaybackDevice:
    devices = miniaudio.Devices()
    playbacks = devices.get_playbacks()
    for playback in playbacks:
        if playback["name"] == name:
            break
    else:
        raise LookupError(f"No playback device named {name} available")

    return miniaudio.PlaybackDevice(
        device_id=playback["id"],
        nchannels=1,
        sample_rate=44100,
        output_format=miniaudio.SampleFormat.SIGNED16,
        buffersize_msec=10,
    )
