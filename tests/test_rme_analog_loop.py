# -*- coding: utf-8 -*-
#
# tools/rme_analog_loop_proof.py's measurement and verdict on known signals: the plan of the signal at both rates, the
# figures read off a return that is the signal delayed, scaled and distorted by known amounts, and the refusal, by
# name, of a return that carries no signal (the loop not wired, or wired to other inputs). No JACK, no hardware: the
# arithmetic the Pi run trusts. The run itself is tools/rme_analog_loop_on_the_pi.sh, by hand, on the Pi.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, "tools")]

import rme_analog_loop_proof as loop  # noqa: E402

PATHS = loop.LoopPaths(out=("zynmixer_chan:input_00a", "zynmixer_chan:input_00b"),
                       main=("zynmixer_bus:output_00a", "zynmixer_bus:output_00b"),
                       back=("system:capture_1", "system:capture_2"),
                       xlr_out=(1, 2), xlr_in=(1, 2))


def returned(plan, delay, gain, h2_db=None, noise_dbfs=None):
    """The planned signal as the loop would hand it back: `delay` samples later, times `gain`, with a second harmonic
    of the tone `h2_db` below it and white noise at `noise_dbfs` (dBFS rms) if given."""
    x = plan.signal * gain
    if h2_db is not None:
        t = np.arange(plan.signal.size) / plan.rate
        seg = plan.segments["tone"]
        h2 = np.zeros_like(x)
        a2 = plan.amplitude * gain * 10 ** (h2_db / 20)
        h2[seg.start:seg.stop] = a2 * np.sin(2 * np.pi * 2 * loop.TONE_HZ * t[seg.start:seg.stop])
        x = x + h2
    if noise_dbfs is not None:
        rng = np.random.default_rng(7)
        x = x + rng.standard_normal(x.size) * 10 ** (noise_dbfs / 20)
    y = np.zeros(x.size + delay)
    y[delay:] = x
    return y[:x.size]


class Plan(unittest.TestCase):

    def test_the_plan_at_both_rates(self):
        for rate in (48000, 96000):
            plan = loop.plan(rate)
            self.assertEqual(plan.rate, rate)
            names = [s.name for s in plan.segments.values()]
            self.assertEqual(names, ["lead", "tone", "gap", "sweep", "tail"])
            self.assertEqual(plan.segments["tone"].stop - plan.segments["tone"].start, 2 * rate)
            self.assertEqual(plan.segments["sweep"].stop - plan.segments["sweep"].start, 3 * rate)
            self.assertEqual(plan.signal.size, sum(s.stop - s.start for s in plan.segments.values()))
            # -20 dBFS: a sine of amplitude 0.1, and nothing louder anywhere
            self.assertAlmostEqual(plan.amplitude, 0.1)
            self.assertAlmostEqual(float(np.abs(plan.signal).max()), 0.1, places=3)
            self.assertAlmostEqual(loop.dbfs(plan.signal[plan.segments["tone"].start:plan.segments["tone"].stop]), -20.0, places=2)


class Figures(unittest.TestCase):

    def test_latency_is_the_delay_of_the_sweep(self):
        plan = loop.plan(48000)
        y = returned(plan, delay=1234, gain=0.5)
        self.assertEqual(loop.latency_samples(plan, y), 1234)

    def test_level_is_the_tone_as_it_came_back(self):
        plan = loop.plan(48000)
        y = returned(plan, delay=300, gain=10 ** (11 / 20))  # +11 dB, as XLR out 1 into mic in 1 at gain 0 reads
        f = loop.channel_figures(plan, y)
        self.assertAlmostEqual(f.level_dbfs, -9.0, places=2)
        self.assertAlmostEqual(f.gain_db, 11.0, places=2)
        self.assertEqual(f.latency_samples, 300)
        self.assertAlmostEqual(f.latency_ms, 300 / 48, places=3)

    def test_thd_n_is_the_distortion_put_in(self):
        plan = loop.plan(48000)
        y = returned(plan, delay=300, gain=1.0, h2_db=-60)
        f = loop.channel_figures(plan, y)
        self.assertAlmostEqual(f.thd_n_db, -60.0, delta=0.3)
        self.assertAlmostEqual(f.thd_n_pct, 0.1, delta=0.01)

    def test_noise_floor_is_the_noise_put_in(self):
        plan = loop.plan(48000)
        y = returned(plan, delay=300, gain=1.0, noise_dbfs=-90)
        f = loop.channel_figures(plan, y)
        self.assertAlmostEqual(f.noise_dbfs, -90.0, delta=0.5)

    def test_balance_is_left_against_right(self):
        plan = loop.plan(96000)
        left = loop.channel_figures(plan, returned(plan, delay=400, gain=1.0))
        right = loop.channel_figures(plan, returned(plan, delay=400, gain=10 ** (-0.5 / 20)))
        self.assertAlmostEqual(loop.balance_db(left, right), 0.5, places=2)


class Verdict(unittest.TestCase):

    def test_a_loop_that_returns_the_signal_is_measured(self):
        plan = loop.plan(48000)
        back = (returned(plan, delay=400, gain=2.0), returned(plan, delay=400, gain=2.0))
        main = (plan.signal * 0.8, plan.signal * 0.8)
        v = loop.verdict(plan, PATHS, main, back)
        self.assertIsNone(v.refusal)
        self.assertEqual(len(v.channels), 2)
        self.assertAlmostEqual(v.main[0].level_dbfs, -20 + 20 * np.log10(0.8), places=2)
        self.assertAlmostEqual(v.channels[0].gain_db, 20 * np.log10(2.0), places=2)

    def test_no_signal_back_is_refused_naming_the_path(self):
        plan = loop.plan(48000)
        silence = np.zeros(plan.signal.size)
        v = loop.verdict(plan, PATHS, (plan.signal, plan.signal), (silence, silence))
        self.assertIsNotNone(v.refusal)
        self.assertTrue(v.refusal.startswith("REFUSED rme-analog-loop: "), v.refusal)
        for word in ("zynmixer_chan:input_00a", "zynmixer_bus:output_00a", "system:capture_1", "XLR OUT 1", "XLR IN 1",
                     "system:capture_2", "XLR OUT 2", "XLR IN 2", "not wired", "48V"):
            self.assertIn(word, v.refusal)

    def test_one_dead_channel_is_refused_naming_that_channel_alone(self):
        plan = loop.plan(48000)
        good = returned(plan, delay=400, gain=2.0)
        v = loop.verdict(plan, PATHS, (plan.signal, plan.signal), (good, np.zeros(plan.signal.size)))
        self.assertIsNotNone(v.refusal)
        self.assertIn("system:capture_2", v.refusal)
        self.assertIn("XLR OUT 2", v.refusal)
        self.assertNotIn("XLR OUT 1", v.refusal)

    def test_no_signal_at_main_is_refused_as_the_chain_s_path(self):
        plan = loop.plan(48000)
        silence = np.zeros(plan.signal.size)
        v = loop.verdict(plan, PATHS, (silence, silence), (silence, silence))
        self.assertIsNotNone(v.refusal)
        self.assertIn("zynmixer_bus:output_00a", v.refusal)
        self.assertIn("zynmixer_chan:input_00a", v.refusal)
        self.assertIn("strip", v.refusal)

    def test_a_clipped_return_is_refused(self):
        plan = loop.plan(48000)
        hot = returned(plan, delay=400, gain=12.0)  # +21.6 dB: the tone at +1.6 dBFS, a full-scale clip
        hot = np.clip(hot, -1.0, 1.0)
        v = loop.verdict(plan, PATHS, (plan.signal, plan.signal), (hot, hot))
        self.assertIsNotNone(v.refusal)
        self.assertIn("clips", v.refusal)
        self.assertIn("PAD", v.refusal)

    def test_the_report_names_the_tier_and_how_it_was_measured(self):
        plan = loop.plan(48000)
        back = (returned(plan, delay=400, gain=2.0), returned(plan, delay=400, gain=2.0))
        v = loop.verdict(plan, PATHS, (plan.signal, plan.signal), back)
        text = loop.report(v, {"jack": "48000 Hz, 256 frames, 3 periods", "card": "RME Babyface Pro"})
        self.assertIn("MEASURED DIGITALLY THROUGH THE ANALOG LOOP (never heard)", text)
        self.assertIn("hardware tier", text)
        self.assertIn("THD+N", text)
        d = v.as_dict()
        self.assertEqual(d["rate"], 48000)
        self.assertEqual(d["refusal"], None)
        self.assertEqual(d["channels"][0]["latency_samples"], 400)


if __name__ == "__main__":
    unittest.main()
