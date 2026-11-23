# The RME analog loop on the Pi: what comes out of XLR OUT 1/2, measured (hardware tier)

MEASURED DIGITALLY THROUGH THE ANALOG LOOP (never heard). The Pi 5 runs Zynthian with an RME Babyface Pro;
a cable loops its XLR OUT 1/2 into its XLR IN 1/2 (48V off, gain 0, PAD off, read from the RME before each
run). A known signal is played into a chain's mixer strip, so it takes the chain's own path to the outputs, and
both ends are captured in the same JACK run: MAIN's digital output, which is what the Pi sends to the DAC, and
the analog return on `system:capture_1/2`. Nobody listened; every figure below is read off the captured samples.

- Tool: `tools/rme_analog_loop_proof.py`, run on the Pi by `tools/rme_analog_loop_on_the_pi.sh` under the Pi
  lock. Signal: 1 s of silence, a 1 kHz tone at -20 dBFS for 2 s, 0.5 s of silence, a 20 Hz..20 kHz logarithmic
  sweep at -20 dBFS for 3 s, 0.5 s of silence. Level: a least-squares fit of the tone in its middle 1.5 s.
  THD+N: the residual after the fit, 20 Hz..20 kHz, against the tone. Latency: the lag of the sweep's
  cross-correlation. Noise: the returned lead silence, 20 Hz to the Nyquist, rms. Polarity: the sign of the
  correlation. `tests/test_rme_analog_loop.py` holds the arithmetic to known signals (delay, gain, a second
  harmonic, noise) and the refusal.
- Path: `rme-loop-proof:out_1/2` -> `zynmixer_chan:input_00a/b` (the strip of chain 4, `PH/MDA Piano`,
  `omx-eq8`, `omx-comp`, `MI`; the piano plays nothing, the signal enters after its effects) -> the strip at
  0.8 -> `zynmixer_bus:output_00a/b` (MAIN at 0.8) -> `system:playback_1/2` -> DAC -> XLR OUT 1/2 -> cable
  -> XLR IN 1/2 -> ADC -> `system:capture_1/2`.
- Pi: Raspberry Pi 5, Zynthian from this fork's `openmixer` branch at 7bb95064, plugin-hostd 0.20.6, omx-plugins
  0.19.3, jackd 1.9.22 with the Pi's own options (`-P 70 -s -S -d alsa -d hw:Pro73107815 -p 256 -n 3 -X raw`),
  at 48 kHz as the Pi runs, and at 96 kHz on a server started with those options at that rate and the Zynthian
  restarted on it. 0 xruns in every run.

## The figures

The gain column is against the -20 dBFS played; the MAIN rows are the digital path alone (strip and bus:
0.8 x 0.8 = -3.88 dB, the fader law); the return rows are the loop. The analog loop alone is the return against
MAIN: DAC, cable, ADC.

### 48 kHz, 256 frames, 3 periods

| point | channel | level (dBFS) | gain (dB) | THD+N | latency | noise floor (dBFS rms) | polarity |
|---|---|---:|---:|---:|---:|---:|---|
| MAIN digital | L | -23.88 | -3.88 | 0.0000 % (-153.2 dB) | 256 samples, 5.33 ms | digital silence | + |
| MAIN digital | R | -23.88 | -3.88 | 0.0000 % (-153.2 dB) | 256 samples, 5.33 ms | digital silence | + |
| analog return | L | -14.39 | +5.61 | 0.0038 % (-88.4 dB) | 842 samples, 17.54 ms | -110.0 | + |
| analog return | R | -14.35 | +5.65 | 0.0037 % (-88.7 dB) | 842 samples, 17.54 ms | -110.1 | + |

The analog loop alone: L +9.48 dB, R +9.52 dB, 586 samples (12.21 ms) of round trip beyond MAIN's. Channel
balance of the return, left against right: -0.04 dB.

### 96 kHz, 256 frames, 3 periods

| point | channel | level (dBFS) | gain (dB) | THD+N | latency | noise floor (dBFS rms) | polarity |
|---|---|---:|---:|---:|---:|---:|---|
| MAIN digital | L | -23.88 | -3.88 | 0.0000 % (-155.0 dB) | 256 samples, 2.67 ms | digital silence | + |
| MAIN digital | R | -23.88 | -3.88 | 0.0000 % (-155.0 dB) | 256 samples, 2.67 ms | digital silence | + |
| analog return | L | -14.36 | +5.64 | 0.0038 % (-88.3 dB) | 804 samples, 8.38 ms | -106.4 | + |
| analog return | R | -14.32 | +5.68 | 0.0037 % (-88.6 dB) | 804 samples, 8.38 ms | -106.5 | + |

The analog loop alone: L +9.51 dB, R +9.55 dB, 548 samples (5.71 ms) of round trip beyond MAIN's. Channel
balance of the return, left against right: -0.04 dB.

What the figures say: the loop gains about +9.5 dB at gain 0 (the XLR outputs are hotter than what the mic
inputs take at 0 dBFS; a tone at -20 dBFS comes back at -14.4), the two channels agree within 0.04 dB, the
distortion plus noise of DAC, cable and ADC together is 0.004 % at this level, the noise floor is -110 dBFS at
48 kHz and -106 dBFS at 96 kHz (the band is twice as wide), the polarity is kept, and the round trip through the
JACK graph is 3 periods plus the converters: 842 samples at 48 kHz, 804 at 96 kHz, of which 74 and 36 samples
are the converters and the USB path beyond the periods. The reports as the tool wrote them, with the JSON:
`docs/rme-analog-loop/loop-48000.md`, `loop-96000.md`, `loop-48000.json`, `loop-96000.json`.

## Red first: the loop that is not there

A return that carries no signal is never a figure. The tool refuses it by name, per channel, with the whole
path on the line. Run against the RME's line inputs 3/4, where nothing is wired
(`docs/rme-analog-loop/red-48000.md`):

> REFUSED rme-analog-loop: no signal on system:capture_3 from zynmixer_chan:input_00a through
> zynmixer_bus:output_00a -> system:playback_1 -> XLR OUT 1 -> XLR IN 3 (-155.2 dBFS): the loop is not wired
> there, or is wired to another input; check the cable XLR OUT 1 -> XLR IN 3, the RME's routing of playback 1 to
> AN1, 48V off and gain 0 on Mic-AN3; [the same for channel 2]. No figure is read off a missing or clipped loop.

A silent MAIN is refused as the chain's strip (muted, down, or not on the MAIN bus); a clipped return is refused
naming the PAD; a JACK server at another rate, a missing port, or 48V, gain or PAD set otherwise are refused
before anything is played.

## Found on the way: XLR OUT 1/2 were mute

The first run on the real loop was refused too: -104.9 dBFS on `system:capture_1/2` while MAIN carried the
signal. The RME's own mixer, as ALSA read it, had `Main-Out AN1` and `Main-Out AN2` at 1 (of 65536) and the
routing `PCM-AN1-AN1` and `PCM-AN2-AN2 Playback Volume` at 0. Routing the playback alone changed nothing;
`Main-Out AN1/AN2` at 32768 made the loop live, and the figures above were read with those four controls at
32768. They were put back to 1 and 0 when the proof was done, so the Pi is as it was found: the XLR outputs of
the owner's Babyface are mute until that output level is set and kept (an ALSA state or a unit of the Pi's: a
job of its own, not this one). Every value as found and every change is in `/root/rme-loop/rme-changes.txt`
on the Pi.

## What this does not prove

- Nothing was heard. The measurement is of the loop, digitally; a listening test is still open.
- The piano chain's effects were not in the path: the signal enters at the strip, after `omx-eq8` and `omx-comp`,
  so the figures are the strip, the bus and the converters, not the plugins.
- The headphone outputs, the ADAT and the SPDIF paths of the RME were not measured.
- One cable, one evening. The figures are of this device and this cable at these settings.
