# Divergence: a restored chain that makes sound gets its mixer strip back

When this fork loads a snapshot, a chain that holds a sound source (a synth, a generator) but no mixer strip
gets one added. Upstream rebuilds the chain's slots exactly as the snapshot lists them.

- Why: the audio autoconnect routes a chain's outputs only through its mixer strip (the `MI` slot). A chain
  without one is skipped, so its outputs stay connected to nothing and the chain is silent. The UI adds the
  strip itself when it creates a chain with a synth, so a snapshot the UI saved has it; one written by hand or
  by a tool may not. On the Pi 5, a snapshot whose chain 4 held only `PH/MDA Piano` brought the chain back
  with `effect_1000:out_1` and `out_2` unconnected and no fader on its strip (#21).
- Where: `zyngine/zynthian_chain_manager.py`, `restore_mixer_strip`, called by `set_state` once a chain's
  slots are built. It adds an `MI` processor, for any engine, and logs a warning naming the chain:
  `The snapshot holds chain 4 without its mixer strip: adding one, so its audio is routed`. The next
  snapshot holds the strip, so the warning comes once per snapshot that lacks it.
- Left as they are: a chain that has its strip, a MIDI chain (no sound source), the main chain, and a chain
  whose synth could not be built when the snapshot loaded (nothing makes sound yet; the next load adds the
  strip once the synth builds).
- The audio autoconnect: `zynautoconnect/unrouted_chains.py`, `say_unrouted`, names in the log a chain that
  still has a sound source and no strip (`Audio autoconnect: chain N has no mixer strip, so its outputs are
  not connected`), once while it stays so, not at every autoconnect, and again if it loses a strip later. It
  routes nothing; it says why nothing was routed.
- What stays upstream's: the creation of a chain, the strip's own behaviour, and the routing of every chain
  that has its strip.
- Held to: `tests/test_chain_mixer_strip.py`, on the chain manager's own `set_state` and a real chain: the
  strip is added and saved, the load says so, no second strip, none for a MIDI chain or a synth that could not
  be built, no busy client left; and the autoconnect's rule, once per chain.
- Proven on a Pi (2026-11-12, Pi 5, plugin-hostd 0.20.3, jackd, zynthian-ui#22): with the snapshot above,
  60 s after start, `effect_1000:out_1` and `out_2` on `zynmixer_chan:input_00a` and `input_00b`,
  `midi_in` still on `ZynMidiRouter:ch3_out`, the warning in the journal, chain 4 saved again with its `MI`,
  and the strip's fader on the screen.
- Not proven here: the audio itself. The connections were read from JACK; nothing was measured or listened to.
  Since then the strip's path to XLR OUT 1/2 has been measured, digitally, through the RME's analog loop:
  `docs/rme-analog-loop-on-the-pi.md`.
- End: the divergence ends when upstream gives a restored chain its strip, or refuses a snapshot without one.
  `restore_mixer_strip`, `unrouted_chains.py` and the test then go.
