from __future__ import annotations
from typing import *

from array import array
import asyncio
from dataclasses import dataclass, field
import sys
import time

from fm.audio import sine_array, get_miniaudio_playback_device
from fm.midi import MidiMessage, get_midi_ports, STRIP_CHANNEL, GET_CHANNEL, NOTE_ON
from fm.notes import note_to_freq

__version__ = "0.1.0"


if TYPE_CHECKING:
    from fm.audio import Audio


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


@dataclass
class Synthesizer:
    polyphony: int
    sample_rate: int
    voices: list[Voice] = field(init=False)
    _note_on_counter: int = 0

    def out(self) -> Audio:
        voice_outs = [voice.out() for voice in self.voices]
        for voice_out in voice_outs:
            next(voice_out)
        mix_down = 1 / self.polyphony
        out_buffer = array("h", [0] * (self.sample_rate // 10))  # 100ms
        want_frames = yield out_buffer
        while True:
            output_signals = [v.send(want_frames) for v in voice_outs]
            for i in range(want_frames):
                out_buffer[i] = int(sum([mix_down * o[i] for o in output_signals]))
            want_frames = yield out_buffer[:want_frames]

    def note_on(self, note: int, velocity: int) -> None:
        try:
            pitch = note_to_freq[note]
        except KeyError:
            return
        volume = velocity / 127
        self.voices[self._note_on_counter % self.polyphony].note_on(pitch, volume)
        self._note_on_counter += 1

    def __post_init__(self) -> None:
        self.voices = [
            Voice(
                wave=sine_array(2048),
                sample_rate=self.sample_rate,
                envelope=Envelope(attack=44, decay=8820),
            )
            for _ in range(self.polyphony)
        ]


@dataclass
class Voice:
    wave: array[int]
    sample_rate: int
    envelope: Envelope
    volume: float = 1.0  # 0.0 - 1.0
    pitch: float = 440.0  # Hz
    reset: bool = False

    def out(self) -> Audio:
        out_buffer = array("h", [0] * (self.sample_rate // 10))  # 100ms
        want_frames = yield out_buffer
        w_i = 0.0
        while True:
            w = self.wave
            w_len = len(w)
            eg = self.envelope
            for i in range(want_frames):
                out_buffer[i] = int(self.volume * eg.advance() * w[round(w_i) % w_len])
                w_i += w_len * self.pitch / self.sample_rate
            if self.reset:
                self.reset = False
                self.envelope.samples_advanced = 0
            want_frames = yield out_buffer[:want_frames]

    def note_on(self, pitch: float, volume: float) -> None:
        self.reset = True
        self.pitch = pitch
        self.volume = volume


async def midi_consumer(queue: asyncio.Queue[MidiMessage], synth: Synthesizer) -> None:
    while True:
        msg, delta, sent_time = await queue.get()
        t = msg[0]
        st = t & STRIP_CHANNEL
        ch = -1
        if st != STRIP_CHANNEL:
            ch = t & GET_CHANNEL
            t = st
        if t == NOTE_ON:
            synth.note_on(msg[1], msg[2])


async def async_main(synth: Synthesizer, midi_in_name: str, channel: int) -> None:
    queue: asyncio.Queue[MidiMessage] = asyncio.Queue(maxsize=256)
    loop = asyncio.get_event_loop()

    try:
        midi_in, midi_out = get_midi_ports(midi_in_name, clock_source=True)
    except ValueError as port:
        raise ValueError(f"MIDI IN port {midi_in_name} not connected")

    def midi_callback(msg, data=None):
        sent_time = time.time()
        midi_message, event_delta = msg
        try:
            loop.call_soon_threadsafe(
                queue.put_nowait, (midi_message, event_delta, sent_time)
            )
        except BaseException as be:
            print(f"callback exc: {type(be)} {be}", file=sys.stderr)

    midi_in.set_callback(midi_callback)
    midi_out.close_port()  # we won't be using that one now

    try:
        await midi_consumer(queue, synth)
    except asyncio.CancelledError:
        midi_in.cancel_callback()


def main() -> None:
    synth = Synthesizer(sample_rate=44100, polyphony=4)
    stream = synth.out()
    next(stream)
    with get_miniaudio_playback_device("BlackHole 16ch") as dev:
        dev.start(stream)
        try:
            asyncio.run(async_main(synth, midi_in_name="IAC fmsynth", channel=1))
        except KeyboardInterrupt:
            pass
