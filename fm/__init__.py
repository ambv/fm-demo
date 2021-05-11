from __future__ import annotations
from typing import *

from array import array
import asyncio
from dataclasses import dataclass, field
import sys
import time

from fm.audio import sine_array, get_miniaudio_playback_device, saturate, INT16_MAX
from fm.midi import MidiMessage, get_midi_ports, STRIP_CHANNEL, GET_CHANNEL, NOTE_ON
from fm.notes import note_to_freq

__version__ = "0.1.0"


if TYPE_CHECKING:
    from fm.audio import Audio, FMAudio


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
    voices: list[PhaseModulator] = field(init=False)
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
            PhaseModulator(
                wave=sine_array(2048),
                sample_rate=self.sample_rate,
            )
            for _ in range(self.polyphony)
        ]


@dataclass
class Operator:
    wave: array[int]
    sample_rate: int
    envelope: Envelope
    volume: float = 1.0  # 0.0 - 1.0
    pitch: float = 440.0  # Hz
    reset: bool = False
    current_note_volume: float = 0.0

    def out(self) -> FMAudio:
        out_buffer = array("h", [0] * (self.sample_rate // 10))  # 100ms
        modulator = yield out_buffer
        mod_len = len(modulator)
        w_i = 0.0
        while True:
            w = self.wave
            w_len = len(w)
            eg = self.envelope
            for i, mod in enumerate(modulator):
                mod_scaled = mod * w_len / INT16_MAX
                out_buffer[i] = int(
                    self.current_note_volume
                    * self.volume
                    * eg.advance()
                    * w[round(w_i + mod_scaled) % w_len]
                )
                w_i += w_len * self.pitch / self.sample_rate
            if self.reset:
                self.reset = False
                self.envelope.samples_advanced = 0
            modulator = yield out_buffer[:mod_len]
            mod_len = len(modulator)

    def note_on(self, pitch: float, volume: float) -> None:
        self.reset = True
        self.pitch = pitch
        self.current_note_volume = volume


@dataclass
class PhaseModulator:
    wave: array[int]
    sample_rate: int
    algorithm: int = 3
    rate1: float = 1.0  # detune by adding cents
    rate2: float = 1.01
    rate3: float = 19.0
    op1: Operator = field(init=False)
    op2: Operator = field(init=False)
    op3: Operator = field(init=False)

    def __post_init__(self) -> None:
        self.op1 = Operator(
            wave=self.wave,
            sample_rate=self.sample_rate,
            envelope=Envelope(attack=48, decay=self.sample_rate),
        )
        self.op2 = Operator(
            wave=self.wave,
            sample_rate=self.sample_rate,
            envelope=Envelope(attack=48, decay=self.sample_rate),
            volume=0.5,
        )
        self.op3 = Operator(
            wave=self.wave,
            sample_rate=self.sample_rate,
            envelope=Envelope(attack=24, decay=self.sample_rate // 12),
            volume=0.2,
        )

    def note_on(self, pitch: float, volume: float) -> None:
        self.op1.note_on(pitch * self.rate1, volume)
        self.op2.note_on(pitch * self.rate2, volume)
        self.op3.note_on(pitch * self.rate3, volume)

    def out(self) -> Audio:
        out_buffer = array("h", [0] * (self.sample_rate // 10))  # 100ms
        zero_buffer = array("h", [0] * (self.sample_rate // 10))  # 100ms
        op1 = self.op1.out()
        op2 = self.op2.out()
        op3 = self.op3.out()
        next(op1)
        next(op2)
        next(op3)
        want_frames = yield out_buffer

        while True:
            algo = self.algorithm
            out3 = op3.send(zero_buffer[:want_frames])
            if algo == 0:
                out2 = op2.send(out3)
                out1 = op1.send(out2)
                want_frames = yield out1
            elif algo == 1:
                out2 = op2.send(zero_buffer[:want_frames])
                for i in range(want_frames):
                    out_buffer[i] = saturate(out3[i] + out2[i])
                out1 = op1.send(out_buffer[:want_frames])
                want_frames = yield out1
            elif algo == 2:
                out2 = op2.send(out3)
                out1 = op1.send(out3)
                for i in range(want_frames):
                    out_buffer[i] = saturate(out1[i] + out2[i])
                want_frames = yield out_buffer[:want_frames]
            elif algo == 3:
                out2 = op2.send(out3)
                out1 = op1.send(zero_buffer[:want_frames])
                for i in range(want_frames):
                    out_buffer[i] = saturate(out1[i] + out2[i])
                want_frames = yield out_buffer[:want_frames]
            else:
                out2 = op2.send(zero_buffer[:want_frames])
                out1 = op1.send(zero_buffer[:want_frames])
                for i in range(want_frames):
                    out_buffer[i] = saturate(out1[i] + out2[i] + out3[i])
                want_frames = yield out_buffer[:want_frames]


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
