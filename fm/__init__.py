from __future__ import annotations

import miniaudio
import time

__version__ = "0.1.0"


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
    stream = miniaudio.stream_file("cowbell.wav", nchannels=1)
    with get_miniaudio_playback_device("BlackHole 16ch") as dev:
        dev.start(stream)
        time.sleep(2.0)
