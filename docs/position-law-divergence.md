# The position law of plugin-hostd controllers

The controllers of the plugin-hostd engine are drawn and nudged by the position law of omx-contract
(`scalePosition` / `scaleValue`), not by the `is_logarithmic` law the other engines use.

- Where: `zyngine/zynthian_position_law.py` reads omx-contract's own Python reader of the law (installed by
  its data package). The plugin-hostd engine hands each linear or log controller its travel
  (`position_law`); `zynthian_controller.py` (nudge) and `zynthian_gui_controller.py` (drawing) branch on
  it. A 20 Hz to 20 kHz frequency control puts 1 kHz at 0.5663 of the arc; the `log10(1 + 9p)` law puts it
  at 0.5.
- It governs every position-to-value mapping of such a controller: drawing, nudge and MIDI CC
  (absolute and relative alike), so a CC sweep lands where the knob draws.
- Unchanged: every other engine (jalv and the rest), CC mapping included. A controller without
  `position_law` takes exactly the existing code path.
- Tested against: `data/scale-vectors.json` from the omx-contract-data package
  (`/usr/share/omx-contract/scale-vectors.json`, or `ZYNTHIAN_OMX_SCALE_VECTORS`), both
  directions within one ulp, in `tests/test_position_law.py`. The tests fail if the file is absent.
- If the other engines adopt the same law, the `position_law` option and the branches can go.
- Checked on a Pi 5 (2026-11-07): the tests pass there against the vectors of omx-contract; a plugin-hostd
  controller over the 20 Hz to 20 kHz range of omx-eq8's band frequency draws 1 kHz at 0.5663 through the
  real drawing code; a controller without `position_law` draws as before; with the `is_logarithmic` law
  put back for the plugin-hostd branch the same draw gives 0.1588 and four tests fail.
- Not checked: the drawing on the Pi's physical screen (the numbers above are the drawing code's output,
  not a photograph), and a scripted step on a log control landing within one step on both surfaces.
