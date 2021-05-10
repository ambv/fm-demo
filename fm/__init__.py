from __future__ import annotations
from typing import *

from array import array
from dataclasses import dataclass
import math
import miniaudio
import time

__version__ = "0.1.0"

INT16_MAX = 2 ** 15 - 1

if TYPE_CHECKING:
    Audio = Generator[array[int], int, None]


def sine_array(sample_count: int) -> array[int]:
    numbers = []
    for i in range(sample_count):
        current = round(INT16_MAX * math.sin(i / sample_count * math.tau))
        numbers.append(current)
    return array("h", numbers)


@dataclass
class Envelope:
    # all units in samples
    attack: int
    decay: int
    samples_advanced: int = 0
    current_value: float = 0.0

    def advance(self) -> float:
        envelope = self.current_value
        a = self.attack
        d = self.decay
        advanced = self.samples_advanced

        if advanced == -1:
            return 0.0

        if advanced <= a:
            envelope = 1.0 if a == 0 else advanced / a
        elif d > 0 and advanced - a <= d:
            envelope = 1.0 - (advanced - a) / d
        else:
            envelope = 0.0
            advanced = -2
        self.samples_advanced = advanced + 1
        self.current_value = envelope
        return envelope


def envelop(audio: Audio, envelope: Envelope) -> Audio:
    result = next(audio)
    want_frames = yield result

    out_buffer = array("h", [0] * want_frames)
    while True:
        mono_buffer = audio.send(want_frames)
        for i in range(want_frames):
            out_buffer[i] = int(envelope.advance() * mono_buffer[i])
        want_frames = yield out_buffer[:want_frames]


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


def main() -> None:
    stream = envelop(endless_sine(100), Envelope(attack=410, decay=44100))
    next(stream)
    with get_miniaudio_playback_device("BlackHole 16ch") as dev:
        dev.start(stream)
        time.sleep(2.0)
