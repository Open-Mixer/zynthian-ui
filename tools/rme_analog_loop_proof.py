#!/usr/bin/env python3
# The RME analog loop of the Zynthian Pi, measured digitally, never heard. The loop is a cable: XLR OUT 1/2 of the
# RME Babyface Pro into its XLR IN 1/2 (48V off, gain 0). A known signal (a 1 kHz tone at -20 dBFS, then a 20 Hz..20 kHz
# sweep at -20 dBFS) is played into a Zynthian chain's mixer strip (zynmixer_chan:input_NNa/b), so it takes the chain's
# own path to the outputs: strip -> MAIN bus -> system:playback_1/2 -> the DAC -> the cable -> the ADC ->
# system:capture_1/2. Both ends are captured in the same run: MAIN's digital output (what the Pi sends to the DAC) and
# the analog return. Off the return, per channel: the level and the gain of the loop, THD+N (20 Hz..20 kHz), the
# round-trip latency, the noise floor, the polarity; and the balance of left against right.
#
# A return that carries no signal is not a figure: it is REFUSED by name (the strip, MAIN, the playback port, XLR OUT n
# -> XLR IN n), per channel, so a loop that is not wired, or wired to other inputs, reads as the missing path and never
# as a quiet DAC. A return that clips is refused naming the PAD. Exit 1 on a refusal.
#
#   python3 tools/rme_analog_loop_proof.py --rate 48000 --chain-strip 0 --json loop-48000.json --report loop-48000.md
#
# Needs the Zynthian's JACK server running at --rate with the chain whose strip is --chain-strip, python3-jack-client and
# numpy. tools/rme_analog_loop_on_the_pi.sh runs it at both rates on the Pi, under the Pi lock, and restores the Pi.
# tests/test_rme_analog_loop.py holds the arithmetic to known signals.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import argparse
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass

import numpy as np

TONE_HZ = 1000.0
AMPLITUDE_DBFS = -20.0  # a sine of amplitude 0.1
SWEEP_HZ = (20.0, 20000.0)
THD_BAND_HZ = (20.0, 20000.0)
NOISE_BAND_LO_HZ = 20.0
FADE_S = 0.001
# Under this the return carries no signal: the loop is not wired there, or is wired to another input
NO_SIGNAL_DBFS = -70.0
CLIP_DBFS = -0.5
MAX_LATENCY_S = 1.0
SEGMENTS_S = (("lead", 1.0), ("tone", 2.0), ("gap", 0.5), ("sweep", 3.0), ("tail", 0.5))


@dataclass
class Segment:
    name: str
    start: int
    stop: int


@dataclass
class Plan:
    rate: int
    amplitude: float
    segments: dict
    signal: np.ndarray


@dataclass
class LoopPaths:
    out: tuple      # the ports the signal is played into: the chain's strip
    main: tuple     # MAIN's digital output ports, what goes to the DAC
    back: tuple     # the capture ports the loop comes back on
    xlr_out: tuple  # the XLR OUT numbers of the cable, per channel
    xlr_in: tuple   # the XLR IN numbers of the cable, per channel


@dataclass
class ChannelFigures:
    level_dbfs: float
    gain_db: float
    latency_samples: int
    latency_ms: float
    thd_n_db: float
    thd_n_pct: float
    noise_dbfs: float
    peak_dbfs: float
    polarity: int


@dataclass
class Verdict:
    rate: int
    paths: LoopPaths
    main: tuple
    channels: tuple
    refusal: object

    def as_dict(self):
        return {"rate": self.rate, "paths": asdict(self.paths), "main": [asdict(c) for c in self.main],
                "channels": [asdict(c) for c in self.channels],
                "balance_db": balance_db(self.channels[0], self.channels[1]) if len(self.channels) == 2 else None,
                "loop_gain_db": [round(self.channels[i].level_dbfs - self.main[i].level_dbfs, 2) for i in range(2)]
                if len(self.channels) == 2 and len(self.main) == 2 else None,
                "refusal": self.refusal}


def dbfs(x):
    """The level of a sine, in dBFS: its amplitude from the rms (a sine of amplitude 0.1 reads -20.00)."""
    rms = float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0
    return 20 * math.log10(rms * math.sqrt(2)) if rms > 1e-12 else -240.0


def dbfs_rms(x):
    """The rms of a signal in dBFS (noise: white noise of standard deviation 1e-4 reads -80.00)."""
    rms = float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0
    return 20 * math.log10(rms) if rms > 1e-12 else -240.0


def _fade(n, rate):
    f = max(1, int(round(FADE_S * rate)))
    w = np.ones(n)
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(f) / f)
    w[:f] = ramp
    w[-f:] = ramp[::-1]
    return w


def plan(rate):
    amplitude = 10 ** (AMPLITUDE_DBFS / 20)
    segments, parts, at = {}, [], 0
    for name, seconds in SEGMENTS_S:
        n = int(round(seconds * rate))
        t = np.arange(n) / rate
        if name == "tone":
            x = amplitude * np.sin(2 * np.pi * TONE_HZ * t) * _fade(n, rate)
        elif name == "sweep":
            lo, hi = SWEEP_HZ
            seconds_ = n / rate
            k = math.log(hi / lo)
            phase = 2 * np.pi * lo * seconds_ / k * (np.exp(t * k / seconds_) - 1)
            x = amplitude * np.sin(phase) * _fade(n, rate)
        else:
            x = np.zeros(n)
        segments[name] = Segment(name, at, at + n)
        parts.append(x)
        at += n
    return Plan(rate, amplitude, segments, np.concatenate(parts))


def latency_samples(plan, back):
    """Where the sweep came back: the lag of the peak of its cross-correlation with the sweep played, 0..MAX_LATENCY_S."""
    seg = plan.segments["sweep"]
    ref = np.zeros(back.size)
    ref[seg.start:seg.stop] = plan.signal[seg.start:seg.stop]
    n = 1 << int(math.ceil(math.log2(back.size + ref.size)))
    c = np.fft.irfft(np.fft.rfft(back, n) * np.conj(np.fft.rfft(ref, n)), n)
    max_lag = min(int(MAX_LATENCY_S * plan.rate), back.size - 1)
    return int(np.argmax(np.abs(c[:max_lag + 1])))


def _polarity(plan, back, lag):
    seg = plan.segments["sweep"]
    a = plan.signal[seg.start:seg.stop]
    b = back[seg.start + lag:seg.stop + lag]
    m = min(a.size, b.size)
    return 1 if float(np.dot(a[:m], b[:m])) >= 0 else -1


def _band(x, rate, lo, hi):
    """x with everything outside lo..hi Hz (and DC) removed."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(x.size, 1 / rate)
    spec[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(spec, x.size)


def _fit_tone(y, rate, hz):
    t = np.arange(y.size) / rate
    basis = np.stack([np.sin(2 * np.pi * hz * t), np.cos(2 * np.pi * hz * t), np.ones(y.size)], axis=1)
    coef, *_ = np.linalg.lstsq(basis, y, rcond=None)
    fit = basis @ coef
    return float(math.hypot(coef[0], coef[1])), fit


def channel_figures(plan, back):
    lag = latency_samples(plan, back)
    rate = plan.rate
    tone = plan.segments["tone"]
    core = int(0.25 * rate)  # the tone's middle: no fades, no settling
    y = back[tone.start + lag + core:tone.stop + lag - core]
    amplitude, fit = _fit_tone(y, rate, TONE_HZ)
    level = 20 * math.log10(amplitude) if amplitude > 1e-12 else -240.0
    residual = _band(y - fit, rate, *THD_BAND_HZ)
    total = _band(y, rate, *THD_BAND_HZ)
    r_rms, t_rms = float(np.sqrt(np.mean(residual ** 2))), float(np.sqrt(np.mean(total ** 2)))
    ratio = r_rms / t_rms if t_rms > 1e-12 else 1.0
    thd_n_db = 20 * math.log10(ratio) if ratio > 1e-12 else -240.0
    lead = plan.segments["lead"]
    quiet = back[lead.start + lag + int(0.1 * rate):lead.stop + lag]
    noise = dbfs_rms(_band(quiet, rate, NOISE_BAND_LO_HZ, rate / 2)) if quiet.size else -240.0
    peak = float(np.abs(back).max()) if back.size else 0.0
    return ChannelFigures(level_dbfs=round(level, 3), gain_db=round(level - AMPLITUDE_DBFS, 3), latency_samples=lag,
                          latency_ms=round(lag * 1000.0 / rate, 3), thd_n_db=round(thd_n_db, 2),
                          thd_n_pct=round(ratio * 100, 4), noise_dbfs=round(noise, 2),
                          peak_dbfs=round(20 * math.log10(peak), 2) if peak > 1e-12 else -240.0,
                          polarity=_polarity(plan, back, lag))


def balance_db(left, right):
    return round(left.level_dbfs - right.level_dbfs, 3)


def verdict(plan, paths, main, back):
    main_f = tuple(channel_figures(plan, np.asarray(m, dtype=float)) for m in main)
    back_f = tuple(channel_figures(plan, np.asarray(b, dtype=float)) for b in back)
    lines = []
    for i, m in enumerate(main_f):
        if m.level_dbfs < NO_SIGNAL_DBFS:
            lines.append("no signal at %s from %s (%.1f dBFS): the chain's strip did not carry it to MAIN; the strip is"
                         " muted, down, or not routed to the MAIN bus, so nothing was sent to system:playback_%d"
                         % (paths.main[i], paths.out[i], m.level_dbfs, paths.xlr_out[i]))
    if not lines:
        for i, b in enumerate(back_f):
            if b.level_dbfs < NO_SIGNAL_DBFS:
                lines.append("no signal on %s from %s through %s -> system:playback_%d -> XLR OUT %d -> XLR IN %d"
                             " (%.1f dBFS): the loop is not wired there, or is wired to another input; check the cable"
                             " XLR OUT %d -> XLR IN %d, the RME's routing of playback %d to AN%d, 48V off and gain 0"
                             " on Mic-AN%d" % (paths.back[i], paths.out[i], paths.main[i], paths.xlr_out[i],
                                               paths.xlr_out[i], paths.xlr_in[i], b.level_dbfs, paths.xlr_out[i],
                                               paths.xlr_in[i], paths.xlr_out[i], paths.xlr_out[i], paths.xlr_in[i]))
        for i, b in enumerate(back_f):
            if b.level_dbfs >= NO_SIGNAL_DBFS and b.peak_dbfs > CLIP_DBFS:
                lines.append("the return on %s clips (%.2f dBFS peak): lower the level played, or engage the PAD on"
                             " Mic-AN%d" % (paths.back[i], b.peak_dbfs, paths.xlr_in[i]))
    refusal = None
    if lines:
        refusal = "REFUSED rme-analog-loop: " + "; ".join(lines) + ". No figure is read off a missing or clipped loop."
    return Verdict(plan.rate, paths, main_f, back_f, refusal)


def report(v, env):
    """A Markdown block for the docs, labelled hardware tier; the refusal verbatim when there is one."""
    rate_khz = v.rate / 1000
    head = ["### The RME analog loop at %g kHz (hardware tier)" % rate_khz, "",
            "MEASURED DIGITALLY THROUGH THE ANALOG LOOP (never heard): a 1 kHz tone at -20 dBFS and a 20 Hz..20 kHz"
            " sweep at -20 dBFS, played into the chain's strip %s, captured at MAIN's digital output %s and on the"
            " return %s, the cable XLR OUT %d/%d -> XLR IN %d/%d, 48V off, gain 0."
            % ("/".join(v.paths.out), "/".join(v.paths.main), "/".join(v.paths.back), v.paths.xlr_out[0],
               v.paths.xlr_out[1], v.paths.xlr_in[0], v.paths.xlr_in[1]), ""]
    for k in sorted(env):
        head.append("- %s: %s" % (k, env[k]))
    if v.refusal:
        return "\n".join(head + ["", v.refusal, ""])
    rows = ["", "| point | channel | level (dBFS) | gain (dB) | THD+N | latency | noise floor (dBFS rms) | polarity |",
            "|---|---|---:|---:|---:|---:|---:|---|"]
    for i, (name, c) in enumerate([("MAIN digital", v.main[0]), ("MAIN digital", v.main[1]),
                                   ("analog return", v.channels[0]), ("analog return", v.channels[1])]):
        side = "L" if i % 2 == 0 else "R"
        noise = "digital silence" if c.noise_dbfs <= -200 else "%.1f" % c.noise_dbfs
        rows.append("| %s | %s | %.2f | %+.2f | %.4f %% (%.1f dB) | %d samples, %.2f ms | %s | %s |"
                    % (name, side, c.level_dbfs, c.gain_db, c.thd_n_pct, c.thd_n_db, c.latency_samples, c.latency_ms,
                       noise, "+" if c.polarity > 0 else "inverted"))
    bal = balance_db(v.channels[0], v.channels[1])
    loop = [round(v.channels[i].level_dbfs - v.main[i].level_dbfs, 2) for i in range(2)]
    rows += ["", "Channel balance of the return, left against right: %+.2f dB. The analog loop alone, the return"
             " against MAIN's digital output (DAC, cable, ADC): L %+.2f dB, R %+.2f dB, %d samples (%.2f ms) of"
             " round trip beyond MAIN's. The MAIN rows are the digital path (strip and bus, no converter); the gain"
             " column is against the -20 dBFS played; the return's latency is the round trip through the JACK graph as"
             " the Pi sees it." % (bal, loop[0], loop[1], v.channels[0].latency_samples - v.main[0].latency_samples,
                                   (v.channels[0].latency_samples - v.main[0].latency_samples) * 1000.0 / v.rate), ""]
    return "\n".join(head + rows)


def card_controls(card):
    """The RME's 48V, gain and PAD of Mic-AN1/AN2 as amixer reads them, or None without the card."""
    if card is None:
        return None
    out = {}
    for n in ("Mic-AN1 48V", "Mic-AN2 48V", "Mic-AN1 Gain", "Mic-AN2 Gain", "Mic-AN1 PAD", "Mic-AN2 PAD"):
        try:
            txt = subprocess.run(["amixer", "-c", str(card), "cget", "name=" + n], capture_output=True, text=True,
                                 check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            return None
        for line in txt.splitlines():
            if ": values=" in line:
                out[n] = line.split("values=", 1)[1].strip()
    return out


def find_card(name_part):
    try:
        with open("/proc/asound/cards") as f:
            for line in f:
                if line[:3].strip().isdigit() and name_part in line:
                    return int(line.split("[")[0])
    except OSError:
        pass
    return None


def run(args):
    import jack  # noqa: E402  the JACK client only here: the arithmetic above has no server

    out_ports = ("zynmixer_chan:input_%02da" % args.chain_strip, "zynmixer_chan:input_%02db" % args.chain_strip)
    paths = LoopPaths(out=out_ports, main=tuple(args.main.split(",")), back=tuple(args.back.split(",")),
                      xlr_out=tuple(int(x) for x in args.xlr_out.split(",")),
                      xlr_in=tuple(int(x) for x in args.xlr_in.split(",")))
    client = jack.Client(args.client_name)
    env = {"jack": "%d Hz, %d frames a period" % (client.samplerate, client.blocksize), "card": args.card_name}
    if args.jack_desc:
        env["jack"] = args.jack_desc
    if client.samplerate != args.rate:
        print("REFUSED rme-analog-loop: the JACK server runs at %d Hz, the proof asked for %d: start it at that rate"
              " first" % (client.samplerate, args.rate))
        return 1
    missing = [p for p in paths.out + paths.main + paths.back if not client.get_ports(p)]
    if missing:
        print("REFUSED rme-analog-loop: not in the JACK graph: %s; the chain whose strip is %d, MAIN and the RME's"
              " capture ports must all be there (zynthian running, the RME its card)" % (", ".join(missing),
                                                                                           args.chain_strip))
        return 1
    card = args.card if args.card is not None else find_card(args.card_name.split()[-1] if args.card_name else "Pro")
    controls = card_controls(card)
    if controls is not None:
        env["rme controls"] = ", ".join("%s %s" % kv for kv in sorted(controls.items()))
        wrong = [n for n, v in controls.items() if ("48V" in n and v != "off") or ("Gain" in n and v != "0")
                 or ("PAD" in n and v != "off")]
        if wrong:
            print("REFUSED rme-analog-loop: the loop is specified with 48V off, gain 0 and PAD off on Mic-AN1/AN2, and the"
                  " RME reads otherwise: %s" % ", ".join("%s=%s" % (n, controls[n]) for n in wrong))
            return 1
    p = plan(args.rate)
    pad = int(MAX_LATENCY_S * p.rate) + client.blocksize * 2
    total = p.signal.size + pad
    outbuf = np.zeros((2, total), dtype=np.float32)
    outbuf[:, :p.signal.size] = p.signal
    inbuf = np.zeros((4, total), dtype=np.float32)
    state = {"i": 0, "done": False, "xruns": 0}
    outs = [client.outports.register("out_%d" % (k + 1)) for k in range(2)]
    ins = [client.inports.register(n) for n in ("main_l", "main_r", "back_l", "back_r")]

    @client.set_process_callback
    def process(frames):
        i = state["i"]
        if state["done"]:
            for o in outs:
                o.get_array()[:] = 0
            return
        n = min(frames, total - i)
        for k, o in enumerate(outs):
            a = o.get_array()
            a[:n] = outbuf[k, i:i + n]
            a[n:] = 0
        for k, port in enumerate(ins):
            inbuf[k, i:i + n] = port.get_array()[:n]
        state["i"] = i + n
        if state["i"] >= total:
            state["done"] = True

    @client.set_xrun_callback
    def xrun(delay):
        state["xruns"] += 1

    with client:
        for k in range(2):
            client.connect(outs[k], paths.out[k])
        client.connect(paths.main[0], ins[0])
        client.connect(paths.main[1], ins[1])
        client.connect(paths.back[0], ins[2])
        client.connect(paths.back[1], ins[3])
        deadline = time.time() + total / p.rate + 10
        while not state["done"] and time.time() < deadline:
            time.sleep(0.05)
        for k in range(2):
            client.disconnect(outs[k], paths.out[k])
    if not state["done"]:
        print("REFUSED rme-analog-loop: the JACK server did not run the %d frames in time (xruns %d)"
              % (total, state["xruns"]))
        return 1
    env["xruns during the run"] = str(state["xruns"])
    main = (inbuf[0].astype(float), inbuf[1].astype(float))
    back = (inbuf[2].astype(float), inbuf[3].astype(float))
    v = verdict(p, paths, main, back)
    text = report(v, env)
    print(text)
    if args.json:
        d = v.as_dict()
        d["env"] = env
        d["measured"] = "MEASURED DIGITALLY THROUGH THE ANALOG LOOP (never heard)"
        with open(args.json, "w") as f:
            json.dump(d, f, indent=1)
    if args.report:
        with open(args.report, "w") as f:
            f.write(text)
    if args.capture_dir:
        os.makedirs(args.capture_dir, exist_ok=True)
        np.save(os.path.join(args.capture_dir, "loop-%d.npy" % p.rate), inbuf)
    return 1 if v.refusal else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="the RME analog loop of the Zynthian Pi, measured digitally")
    ap.add_argument("--rate", type=int, required=True, help="the JACK rate the proof is for (refused at another)")
    ap.add_argument("--chain-strip", type=int, default=0, help="the mixer strip (zynmixer_chan:input_NN) the signal is played into")
    ap.add_argument("--main", default="zynmixer_bus:output_00a,zynmixer_bus:output_00b", help="MAIN's digital output ports")
    ap.add_argument("--back", default="system:capture_1,system:capture_2", help="the capture ports the loop returns on")
    ap.add_argument("--xlr-out", default="1,2", help="the XLR OUT numbers of the cable, per channel")
    ap.add_argument("--xlr-in", default="1,2", help="the XLR IN numbers of the cable, per channel")
    ap.add_argument("--card", type=int, default=None, help="the ALSA card of the RME (found by --card-name when unset)")
    ap.add_argument("--card-name", default="RME Babyface Pro")
    ap.add_argument("--jack-desc", default=None, help="how the JACK server was started, for the report")
    ap.add_argument("--client-name", default="rme-loop-proof")
    ap.add_argument("--json", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--capture-dir", default=None, help="keep the four captured channels here (.npy)")
    args = ap.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
