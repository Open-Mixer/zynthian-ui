# The vintage controller drawn with Tk (zynthian-ui#93)

Status: design, not built; the owner's rulings of 2026-11-20 are in (section 6, "Decided"). It replaces
`docs/ui-look-drawn-widgets.md` (zynthian-ui#53, #74, #79) when its last stage lands. The rulings widen #93 from
the controller to the plugin panel: both are drawn in Tk, and the ctypes door to `libomx-panel-render.so.0` goes once
both are.

Owner rule, 2026-11-19: each toolkit draws its own. Zynthian draws its controllers with its own toolkit, Tk (and PIL,
which stock Zynthian already draws with: `zyngui/zynthian_gui_mixer.py`, `zynthian_gui_dpm.py`,
`zynthian_gui_selector_grid.py`). From omx-panel it reads shared BEHAVIOUR only (gestures, scale laws, steps, value
text: omx-panel `docs/behaviour-core.md`, `docs/panel-gestures.md`), never omx-panel's pixels. omx-panel's own spec
says the same: "Each toolkit draws: ... Zynthian in Tk and PIL (its plugin panels still come through this repository's
renderer, until it draws them itself)" (omx-panel `docs/behaviour-core.md:26`).

Every `file:line` below is this branch's base (`origin/openmixer` 0d7681bf) unless another repository is named. omx-panel
lines are from its checkout at 54e8f90, zynthian-sys lines from 79958b4.

## 1. What the drawn controller does today

### The switch and the class

- `ZYNTHIAN_UI_LOOK` is read once as `ui_look`: `stock` or `vintage`, any other word refused by name and read as
  `stock` (`zyngui/zynthian_gui_config.py:565-568`). zynthian-sys's look files export it
  (`config/ui-looks/openmixer-vintage.sh:27`, `config/ui-looks/stock.sh:25`).
- Under `vintage` the module's tail rebinds the name `zynthian_gui_controller` to `drawn_controller(base)`
  (`zyngui/zynthian_gui_controller.py:876-880`); every screen that constructs a controller (`zynthian_gui_control.py:74`,
  `zynthian_gui_selector.py:255`, `zynthian_gui_engine.py:589`, the config screens) gets it. Under `stock` the drawn
  module is never imported.
- The subclass overrides only what paints: `config`, `show`, `on_size`, `plot_value`, `set_title`, `_set_color_graph`,
  `zynpot_abs` (`zyngui/zynthian_gui_controller_drawn.py:86-120`). The zynpot, the touch gestures
  (`zynthian_gui_controller.py:785-872`, with `set_drag_scale` at `:208-230`), the value's reading and text
  (`calculate_plot_values`, `:407-466`) and the MIDI-bind text are upstream's, inherited.

### Per widget kind

`widget_kind` (`zynthian_gui_controller_drawn.py:50-56`) picks one of four kinds; `description` (`:59-62`) makes a
one-control panel of it, opened as an omx-panel `View` in the look (`:158-175`), read (`:197-204`), drawn to RGBA by
`libomx-panel-render.so.0`, composited over `color_panel_bg` with PIL and shown as ONE canvas image (`:206-220`). The
stock graph, title and value items are hidden (`:154-155`).

| kind | chosen when | reading given to the renderer | what the renderer draws (omx-panel `renderer/src/view.c`) |
|---|---|---|---|
| `knob` | numeric, no ticks (`:56`) | `set_value(value_plot, value_print)` (`:204`); `set_travel(min, max, default, step, log, int)` (`:168-170`) | under the vintage style the look's drawing `knob-vintage` as a scene (`view.c:845-850`, omx-panel `tools/look.json:114`, `"--knob": "knob-vintage"` at `:900`): an 11-tick legend ring over -135..+135 degrees, a drop shade, the rim in `--knob-edge`, the knurl disc in `--knob-knurl` with 24 knurl lines every 15 degrees, the cap as a radial gradient `--knob-cap-hi` to `--knob-face` (focus 0.35, 0.3), and the pointer as three lines (a shaded groove wall, a lit wall, the pointer in `--knob-pointer`) rotated by the value. Under a flat look: rim disc, body disc, one pointer segment (`view.c:852-856`). Travel 270 degrees (`KNOB_DEG`, `zynthian_gui_controller_drawn.py:46`). |
| `switch` | two ticks (`:55`; PR #89 adds "unless the engine said `is_toggle: False`", `toggle_declared`) | `set_value(index, label)` | a pill, `h/2` radius, `--accent` on / body off, a thumb disc at the end (`view.c:882-886`), on from 0.5 |
| `selector` | more than two ticks | `set_choice(index, count, label)` (`:200`) | a rounded rect in the rim colour, the body inside, a 2 px accent segment under the chosen slot (`view.c:859-864`) |
| `display` | a path, or a selector counter (`:52-53`) | `set_value(0, 0, value_print)` (`:202`) | the reading frame: rim, body, no travel (`view.c:876-880`); the text is the renderer's, in its font |
| label, value text | always | the title (`set_title`), `value_print` | the renderer's label under the control (`--ink-dim`) and value (`--ink`), in its own font (Inter) |

What stays Zynthian's own on top of the image:

- the selection: a 2 px canvas rectangle in the colour the stock arc would take, none when unselected
  (`FRAME_PX`, `:43`; `_set_color_graph` `:109-112`; `frame` `:227-237`); readonly and disabled take
  `color_ctrl_bg_off` the same way;
- the pickup marker: upstream's `graph_pickup` arc, moved onto the renderer's knob box (`view.target_rect(0)`) at 12
  degrees, 2 px outside the rim, over 270 degrees (`place_marker`, `:177-195`); none on a control without a knob;
- the MIDI-bind text, raised above the image (`:217-218`);
- the blank slot (`blank`, `:239-253`) and the fall-back to stock items when the renderer is absent, refuses the look
  or stops (`fall_back`, `:255-275`), said once;
- the thread hop: every renderer call is made on Tk's thread (`panel_view.in_owner_thread`,
  `zyngine/zynthian_omx_panel_view.py:286`), a draw asked from the CUIA thread is posted with `after_idle` (`:125-129`),
  because the renderer's socket carries one call at a time (zynthian-ui#79).

The look palette: `zyngine/zynthian_ui_look.py` `ROLES` (`:27-31`) values eleven renderer roles from
`zynthian_gui_config` colours; `tokens` (`:44-54`) lays them over omx-panel's `tools/look.json` and `look_for` (`:57`)
caches it. The base file, its `style` (`vintage`), its finish (`aluminium`) and its `drawings` are omx-panel's, so the
metal of today's vintage knob comes from omx-panel's file, not from Zynthian's palette: the level-1 preset carries no
knob token (zynthian-sys `config/ui-looks/openmixer-vintage.sh`, sixteen colours, the font and six grid tokens).

The size: on the Pi a controller cell is 256 x 176 px; the one-control panel is drawn at the renderer's own size,
120 x 165 px at the cell's left, its knob a third of the stock arc's diameter (`docs/ui-look-drawn-widgets.md:213-216`).
The stock arc in that cell has radius `min(w, h) // 2 - 4` = 84 px and stroke `radius // 4` = 21 px
(`zynthian_gui_controller.py:236-239`, `:269-270`).

### What omx-panel's renderer contributes, and Tk must now draw itself

1. The vintage knob: tick ring, shade, rim, knurl disc and knurl lines, the radial cap gradient (the cap highlight),
   the carved pointer (three lines).
2. The value text and the label in the renderer's font (Tk already draws both: the stock `label_title` and
   `value_text` items, `zynthian_gui_controller.py:163-173`, with upstream's fitting in `set_text` `:583-622` and
   `calculate_value_font_size` `:631-689`).
3. The pill switch, the selector strip, the reading frame (display).
4. The panel's own face behind a one-control description (the "head" that omx-panel#94 was to remove): Tk drops it;
   the controller's ground is `color_panel_bg`, the canvas's own `bg` (`zynthian_gui_controller.py:118-123`).

## 2. The Tk drawing plan

### Principles

- Zynthian draws from LOOK TOKENS it owns, delivered as `zynthian_gui_config` colours the way the grid's are
  (`ZYNTHIAN_UI_COLOR_GRID_*`, zynthian-ui#55): the vintage preset in zynthian-sys gains the knob's metal from the
  console's `tokens.css` (the same pin that generates the preset today), as `ZYNTHIAN_UI_COLOR_KNOB_FACE`, `_EDGE`,
  `_CAP_HI`, `_KNURL`, `_POINTER`, plus the switch track and thumb. Under `stock` they are not read and stock draws
  upstream's arc. Under `vintage` a preset with any of them unset is refused by name and the stock widget is drawn,
  as an unknown `ZYNTHIAN_UI_LOOK` word is today (`zynthian_gui_config.py:566-568`): no default, no compat path for
  an older preset. No Zynthian file reads omx-panel's `tools/look.json`.
- Static layers are drawn ONCE per (kind, size, tokens) and cached; a value change moves canvas items only (`coords`,
  `itemconfig`), with no image conversion per value. This is what today's path cannot do: every new value is a
  renderer draw, a PIL composite and a new `PhotoImage` (`zynthian_gui_controller_drawn.py:144-153`, `:206-216`).
- Tk's canvas has no gradient and no anti-aliasing on X11. The metal is therefore a PIL image made by Zynthian's own
  code from the tokens, supersampled and reduced (anti-aliasing), and the moving parts are canvas items.
- The stock widget's items stay the text: `label_title`, `value_text`, `midi_bind` and `graph_pickup` keep upstream's
  fonts, fitting and colours; the Tk look adds items, it never re-implements text fitting.

### The knob (numeric controller)

Geometry: the stock arc's own box (`on_size_arc`, `zynthian_gui_controller.py:233-276`): centre `(x0, y0)`, outer
radius `radius`. The knob's diameter is `2 * radius` (168 px in the Pi's 256 x 176 cell, against 48 to 64 px drawn by
the renderer today), so the value text sits on the cap where upstream places it in the arc's interior
(`value_width = 2 * (radius - arc_width - 1)`, `:240`). The proportions are Zynthian's own, written in its module
and checked against a reference picture (ruling Q2): omx-panel's MOD GUI vintage renders, committed in omx-panel as
`docs/shots/mod-ui-1.15.0-container-strip-vintage-advanced.png` (omx-strip) and
`docs/shots/mod-ui-1.15.0-container-comp-vintage-metal-closeup.png` (the knob's metal at device scale 4, omx-panel
`docs/shots/README.md:9,12`). The owner's shot archive (`openmixer-shots/modgui/`) is not reachable from this lane's
host; the stage-1 lane uses the committed shots, or is handed the archive's omx-strip render. Starting values, to be
fixed by measuring the picture: tick ring 0.97 to 0.86 of the radius, rim 0.81, knurl 0.73, cap 0.70, pointer 0.21 to
0.63. No Zynthian code reads omx-panel's drawing; the picture is a test reference, not an input.

- Layer 1, the face: one PIL `RGBA` image of `2 * radius` square, drawn at 3x and reduced with `LANCZOS`: tick ring
  (11 lines over -135..+135 in `color_hl`, the `--legend` the preset already maps), the shade (a disc offset 1/48 down,
  black at 50 %), the rim (`KNOB_EDGE`), the knurl disc and its 24 lines (`KNOB_KNURL`), the cap: the radial gradient
  approximated by N concentric discs stepping from `KNOB_FACE` (outer) to `KNOB_CAP_HI` (inner), each disc's centre
  moving toward the focus (0.35, 0.3), N = 24 (a step every 0.7 px at 168 px: no visible banding after the
  reduction). Cached by `(2 * radius, tokens)`; shown as one `create_image` under every other item, built at
  `on_size` and never at a value.
- Layer 2, the pointer: three `create_line` items (shaded wall, lit wall, pointer) with `capstyle=ROUND`, moved by
  `coords` at each `plot_value` from the angle `-135 + 270 * value_plot`. A line drawn by Tk is aliased; at 2 to 4 px
  width on a 168 px knob that is checked in stage 1's shot against the reference picture. If it is refused, the
  pointer becomes a small rotated PIL sprite per value (one `PhotoImage` per value, the cost today's path pays).
- The value arc: upstream's `graph` arc is not shown (the knob IS the value); the travel ring stays the tick legend.
  A bipolar control (`value_min <= 0 <= value_max`, `plot_value_arc` `:525-526`) shows its zero tick in `color_on`.
- The pickup marker: upstream's `graph_pickup` arc, placed 2 px outside the rim (the tick ring's radius), 12 degrees,
  over the same 270 degrees as the pointer: the code of `place_marker` (`zynthian_gui_controller_drawn.py:191-195`)
  without `target_rect`, the box being the knob's own.
- Selected: the 2 px frame of today (`frame`, `:227-237`), unchanged.

PIL draws the face (ruling Q3: Zynthian's toolkit is Tk and PIL), cached per size. PIL is installed on the Pi
(`python3-pil`, `python3-pil.imagetk` 11.1.0, queried 2026-11-20) and stock Zynthian already imports it. No
pure-canvas variant is built.

### The switch (two-value list)

A pill: two `create_oval` caps and one `create_rectangle` in the track colour (`--switch-track`, a preset token), a
thumb `create_oval` in `--switch-thumb`, at the left (off) or the right (on, track in `color_on`). Value change: `coords`
of the thumb and `itemconfig` of the track: no image. Size: the console's ratio 40 x 20 (omx-panel
`tools/look/geometry.json:6` gives the console's proportion; Zynthian writes its own numbers) scaled to the arc box's
width, the label above and the value text below as upstream places them. Aliased ovals at 20 to 40 px are visible;
if the stage-2 shot is refused, the pill becomes a cached PIL image per state (two images per size).

### The selector (more than two values)

A rounded strip (a `create_polygon` with `smooth=True` and a rect) in `color_panel_hl`, N segment ticks, and the
chosen segment as one `create_rectangle` in `color_on` moved by `coords`; the label of the choice is upstream's
`value_text`. Upstream's arc segment for a list (`plot_value_arc` `:519-524`) is not shown.

### The display (path, selector counter): the LCD readout

The console's glass: a cached PIL image of the recessed screen (`--glass` ground `color_off`, an inner shadow by two
stepped insets, the 12 px grid at 10 % `--legend` that `--screen-bg` declares) behind upstream's `value_text` drawn in
`color_on` (the scribble ink of the console's vintage look). Built at `on_size`, never at a value.

### Label and value text

Upstream's items and fitting, in the preset's font (`ZYNTHIAN_UI_FONT_FAMILY`). The colours are the palette's:
title `color_panel_tx`, value `color_ctrl_tx` (as stock, `zynthian_gui_controller.py:163-173`).

### Cost on the Pi 5

Measured on the Pi 5 (4 cores, arm64) with `pi-evidence.sh` (labels `zynthian-ui-93-knob-face-bench`,
`zynthian-ui-93-knob-face-bench-ss`), a PIL script of the face as specified above (ticks, shade, rim, knurl disc and
lines, 24 cap discs), mean of 20 draws, the conversion to a Tk `PhotoImage` not included (no display in the run):

| face size | 2x supersample | 3x | 4x |
|---|---|---|---|
| 48 px | | | 2.19 ms |
| 64 px | 1.44 ms | 2.22 ms | 3.35 ms |
| 126 px | | | 11.04 ms |
| 168 px | 6.47 ms | 12.03 ms | 18.85 ms |

For comparison, omx-panel's CPU renderer drew a 64 px knob in 4.9 ms uncached and 0.33 ms cached (the earlier
measurement). The face is drawn once per size and token set: four controllers at 168 px at 3x cost about 48 ms once,
at a page's first draw in a new size (a resize, a layout change), and nothing per value. Per value the cost is
three `coords` calls on line items, with no PIL, no `PhotoImage`, no socket; it is measured in stage 1 on the Pi
(target: p99 under 1 ms per controller update, against today's renderer draw + composite + `PhotoImage` per value).
The cache can be warmed at start for the layout's one cell size. The conversion of a 168 px image to `PhotoImage` is
expected to be well under a millisecond (`docs/blit-per-frame-on-the-pi.md` measured 5 to 8 ms for a 1024 x 416 frame,
about 15 times more pixels) and is measured in stage 1.

### The plugin panel in Tk (ruling Q4)

Today a plugin whose panel has a bar group, a curve or a meter (`drawn_parts`, `zynthian_omx_panel_view.py:592-594`)
gets its own screen, `zyngui/zynthian_widget_omx_panel.py` (`set_drawn_view`,
`zynthian_engine_plugin_hostd.py:1377-1386`). The engine reads two documents from `omx-panel describe` as JSON: the
layout (`--layout`) and the description (`panel_drawn_with`, `:1172-1200`). The widget cuts the screen's part
(`screen_part`, `zynthian_omx_panel_view.py:597-619`), opens a renderer `View` in the look (`zynthian_widget_omx_panel.py:140-179`),
gives it values (`fraction` through the position law, `:181-185`; `set_value`/`set_choice`, `:198-203`), curves
(`engine.curve`, plugin-hostd's `curve_points`, `zynthian_engine_plugin_hostd.py:1388-1414`) and meters
(`engine.meter`, the feedback port, `:1416-1428`). It blits the RGBA (`paint`, `zynthian_widget_omx_panel.py:221-227`) and
sends pointer, wheel and keys to the renderer's gesture unit (`drawn_input`, `:229-292`). Without the renderer it
draws strips in Tk (`refresh_gui`, `:308-336`), moved by `zynthian_panel_gestures.Panel` (`:88-91`). Strips are the
interim on any image without `libomx-panel-render0` until this lands (ruling Q5).

The Tk panel reads the same two documents as DATA, never as pixels. They come from `omx-panel describe` as today, which
reads the descriptions store by key (omx-panel `docs/descriptions-store.md:42`); Zynthian keeps calling `describe` and
reads no store file itself. What it needs from them, all present in what the engine already reads:

- `sections[]` (key, label, `bars` for a bar group), `controls[]` (symbol, label, section, `standard.widget`),
  `displays[]` (kind, section), `meters[]` (symbol, label, range, unit), `roles[]` (for `curve_bind_line`,
  `zynthian_omx_panel_view.py:641-660`); the page cut stays `screen_part`.
- No geometry from omx-panel: Zynthian lays the screen's sections out in its own numbers (rows of controls in the
  screen's width, a curve's section on top as `screen_part` keeps it), not from omx-panel's `tools/look/geometry.json`.

What it draws, each with the controller's Tk pieces of this note:

- a knob, switch or selector control: the controller's drawing (the same face cache, the same tokens);
- a bar group: one Tk rectangle per bar, the fill moved by `coords`, the input through `zynthian_panel_gestures.BarGroup`
  as the drawbar already does (`zyngui/zynthian_widget_drawbar.py:4`, `:51`);
- a curve: its frame and grid as cached PIL or canvas items, the points from `curve_points` as one `create_line`
  polyline moved by `coords`, a band's handle as an oval moved by the `handle` gesture of `zynthian_panel_gestures`;
- a meter: a rectangle filled to the reading and a peak mark.

Two things the renderer does today that are not drawing, and that Zynthian must get as behaviour, not write itself:

- the curve's axes: `draw_curve` maps the points onto the frame (omx-panel `renderer/src/view.c:1028`), with a log
  frequency axis that the renderer derives from the kind's name (`log_x = strcmp(kind, "eq_response") == 0`,
  `view.c:411`). The description does not carry it. Stage 2 waits for omx-panel to publish
  it in the description (section 6, Q7).
  Zynthian types no rule for it;
- the meter's ballistics: the renderer takes `set_meter(value, elapsed)`. omx-panel's behaviour core names it as
  omx-dsp's view law (`omx_meter_view_step`, `docs/behaviour-core.md` section 1). Zynthian has no Python door to it
  today. Stage 2 waits for a ctypes door to it (section 6, Q6).

## 3. The shared-behaviour boundary

What the controller reads from outside Zynthian today, and through what:

| behaviour | read through | by the controller? |
|---|---|---|
| the position law (lin, log, stepped, map) | `zyngine/zynthian_position_law.py:20`, a re-export of `omx_contract.scale` (python3-omx-contract), used in `calculate_plot_values` (`zynthian_gui_controller.py:433-434`) and by the controller's MIDI and nudge paths (`zyngine/zynthian_controller.py:436-440`, `:602-609`, `:686-687`, `:728-730`) for a controller that carries a `position_law` travel (`zynthian_controller.py:89`, `:192-193`, plugin-hostd only) | yes: `value_plot`, the pointer's angle |
| the step | `position_law["step"]`, passed to the renderer by `set_travel` (`zynthian_gui_controller_drawn.py:168-170`) | only to the renderer, which does not move this controller: the gestures are upstream's (`zynthian_gui_controller.py:785-872`). The Tk version passes it nowhere. |
| the gestures | `zyngine/zynthian_panel_gestures.py` reads omx-panel's `schema/gestures.json` (`:5-10`, `table_path` `:43-60`); used by the drawbar (`zynthian_widget_drawbar.py:4`), the XY screen (`zynthian_gui_control_xy.py:33`), the plugin panel's strips (`zynthian_widget_omx_panel.py:31`, `:88-91`) | no: the stock controller keeps upstream's drag, wheel and zynpot. The Tk plugin panel moves onto it entirely: the renderer's gesture unit (`drawn_input`) goes |
| toggle or list | the engine's word: `is_toggle`, and `toggle_declared` (PR #89, not merged) | yes: the kind (switch or selector) |
| value text | Zynthian's own: `format_print`, `labels`, `get_value2index` (`zynthian_gui_controller.py:410-464`); the panel's `get_value2label` (`zynthian_widget_omx_panel.py:203`) | yes, as upstream |

The design keeps that boundary exactly: the Tk controller reads `value_plot` and `value_print` as upstream computes
them, the kind from the engine's word, and the Tk panel its controls' description and the gesture table. It proposes
nothing new in omx-panel. When omx-panel's behaviour core lands (its `docs/behaviour-core.md` section 7, step 4:
`zynthian_panel_gestures.py` and `zynthian_position_law.py` become an adapter over `python3-omx-panel-behaviour`),
positions, steps and value text move to that adapter in that step's own lane, not in #93.

One finding on the boundary: two classifiers of a controller's kind exist. `widget_kind` says "two ticks is a switch"
(`zynthian_gui_controller_drawn.py:55`) while `zynthian_panel_gestures.widget_of` says "`is_toggle` is a switch, ticks
a selector" (`zyngine/zynthian_panel_gestures.py:662-666`). Upstream sets `is_toggle` from two labels too, which is
why #89 adds `toggle_declared`. Stage 1 makes them ONE function used by both, so the drawing and the gesture table
cannot disagree on a control.

## 4. What is removed, and when

The `stock`/`vintage` switch STAYS (ruling Q1): `stock` is upstream's arc to the pixel, `vintage` is Zynthian's Tk
drawing (`zynthian_gui_config.py:565-568`, the tail `zynthian_gui_controller.py:876-880`). Upstream compatibility is
kept until the final release, and with it `StockIsUpstream` (`tests/test_ui_look_widgets.py:297-332`). What goes is the
renderer as the meaning of `vintage`.

### With stage 1 (the controller)

- `zyngui/zynthian_gui_controller_drawn.py`, whole: its renderer calls (`View`, `description`, `open_view`,
  `give_reading`, `paint`, `show_image`), `fall_back` on `RendererAbsent`/`RendererStopped`/`LookShort`, and the
  `after_idle` hop for renderer calls (`:116-120`, `:124-129`). The hop existed because the renderer's socket takes
  one call at a time (zynthian-ui#79). The Tk controller keeps the stock widget's threading. A value set from any
  thread only marks the controller dirty. The plot task draws it on Tk's thread (`plot_zctrls_task`,
  `zynthian_gui.py:2885-2897`, every 32 ms; `plot_zctrls`, `zynthian_gui_control.py:618-629`). The one Tk call the stock widget
  already makes from the CUIA thread is the pickup marker (`cuia_zynpot_abs`, `zynthian_gui.py:1709-1712`, to
  `zynthian_gui_control.py:579-581`, to `zynthian_gui_controller.py:752-756`). A stage-1 test holds this. `widget_kind`
  (merged with `widget_of`), `frame` and the marker's arithmetic move into the Tk look's module.
- The controller's use of `zynthian_ui_look` (`zynthian_gui_controller_drawn.py:40`, `:164`, `:171`): the controller
  takes its tokens from `zynthian_gui_config`, as the grid does.
- Tests: in `tests/test_ui_look_widgets.py` the classes `DrawnController` (`:348-585`), `RealRenderer` (the pixel tests
  of zynthian-ui#74, `:587-661`) and `WhatCIMustHave`'s renderer row (`:343-346`); in
  `tests/test_omx_panel_renderer_race.py` the controller rows (`ControllerHarness`, `TheLookAfterAStop`,
  `TheRendererIsTksThreads`, `:250-421`). PR #89's `tests/test_controller_toggle_declared.py` keeps its controller
  half (the engine's word on `zynthian_controller`); its drawn-widget half moves to the Tk test.
- CI: `.github/workflows/tests.yml:132-133` (the skip guard: "no PIL|no omx-panel tools directory") is rewritten for
  the Tk tests; `tools/restated_declarations.py:97` drops `zyngui/zynthian_gui_controller_drawn.py`.

### With stage 2 (the plugin panel)

- In `zyngui/zynthian_widget_omx_panel.py` the renderer path: `build_drawn` (`:140-179`), `refresh_drawn`
  (`:187-219`), `paint` and `PanelImage` (`:221-227`), `drawn_input` and the renderer's key and event codes
  (`:229-292`), `renderer_stopped` (`:299`) and the strips' "renderer stopped" text (`:320-322`). The strips stay
  until the Tk panel draws the same screen, then go too.
- The panel's use of `zynthian_ui_look` (`:34`, `:154-159`).

### With stage 3 (the door)

- `zyngine/zynthian_omx_panel_view.py`: the ctypes door (`LIBRARY`, `:41`; `library`, `_declare`, `_LibraryView`,
  the renderer's process `_serve` and `_Host`, `View`, `PanelImage`, `look_dir`, `tools_dir`, `in_owner_thread`). Its
  data helpers are not pixels and move to a module of their own: `drawn_parts`, `screen_part`, `curve_words`,
  `curve_bind_line`, `curve_points`, `output_set` (`:592-685`), with their tests (`tests/test_omx_panel_view.py`
  `ScreenPart`, `CurveBinding`, `Feedback`). The engine's import changes (`zynthian_engine_plugin_hostd.py:39`).
- `zyngine/zynthian_ui_look.py` (no user left). If PR #88 lands first, `cpu_colour` moves to the Tk look's module with
  the three meter colours it reads.
- Tests: `tests/test_omx_panel_view.py` `Drawn` (`:174-250`), `test_omx_panel_renderer_crash.py`,
  `test_omx_panel_renderer_race.py`, `test_omx_panel_dirty_blit.py`, `tests/omx_panel_widget_stub.py`, the look-table
  classes of `tests/test_ui_look_widgets.py` (`:663-800`), and the renderer rows of `test_plugin_hostd_drawn.py` and
  `test_control_blank_slot_panel.py` (rewritten against the Tk panel in stage 2).
- CI: the renderer's build and environment in `tests.yml` (`:101`, `:108-109`: `make ... libomx-panel-render.so.0`,
  `ZYNTHIAN_OMX_PANEL_RENDER`, `ZYNTHIAN_OMX_PANEL_TOOLS`). The gesture declaration and the real `describe`
  (`:91-99`, `:102-107`) stay.
- Pi tools and docs: `tools/pi/drawn_panel_on_the_pi.py`, `tools/pi/blit_per_frame_on_the_pi.py`,
  `docs/blit-per-frame-on-the-pi.md`, `docs/ui-look-drawn-widgets.md`; this note becomes the look's note.

### Packaging

zynthian-ui has no `debian/` and no install recipe of its own. zynthian-sys installs `omx-panel` and
`python3-omx-contract` (`config/openmixer-packages`). omx-panel stays needed for its `schema/gestures.json`, `describe` and
`omx-modgui-sync`. `libomx-panel-render0` is not in that list (omx-panel `debian/control:41-45`: it depends on
`omx-panel`, not the reverse), and it is NOT added (ruling Q5). The Pi has 0.13.8 installed (queried 2026-11-20); a
fresh image draws plugin panels as strips until stage 2.

## 5. Staged lanes

Each stage: one PR on `openmixer`, the red commit first (tests that fail on the base), then the green; the failing
line and the run in the PR body. Tests run in CI without a display: the canvas is the recording stand-in the look
tests already use (`tests/test_ui_look_widgets.py` `Canvas`, `:94`), the PIL images are real (CI installs
`python3-pil`). Pi proofs run under the Pi evidence runner (`pi-evidence.sh <label> <cmd>`), one at a time, in its
scratch dir, never touching the running UI.

0. **zynthian-sys: the tokens in the vintage preset.** Red: `tests/ui-looks-check.sh` asks for
   `ZYNTHIAN_UI_COLOR_KNOB_FACE`, `_EDGE`, `_CAP_HI`, `_KNURL`, `_POINTER`, `_SWITCH_TRACK`, `_SWITCH_THUMB` in
   `config/ui-looks/openmixer-vintage.sh`, valued from the console's pinned `tokens.css` (aluminium finish). Green: the
   generator emits them; the pin recomputes. `stock.sh` carries none: stock does not read them.
1. **zynthian-ui: the controller in Tk and PIL, all four kinds.** Red:
   - the refusal: under `vintage`, a preset with any knob token unset is refused by name in the log and the stock
     widget is drawn, as an unknown `ZYNTHIAN_UI_LOOK` word is (`zynthian_gui_config.py:566-568`); no default is
     invented;
   - the one switch rule: one function gives the kind to the drawing and to `zynthian_panel_gestures`; a
     `toggle_declared: False` two-value list is a selector in both;
   - structure, per kind: the knob makes one face image and three pointer lines, and a new value moves the pointer's
     `coords` to `-135 + 270 * value_plot` and makes no image. The pill, the selector strip and the display glass make
     their items, and a value moves items only. Each face is built once per size and token set. The stock graph arc
     is hidden; title, value, MIDI bind and pickup marker stand above the face. The frame, the blank slot, the hidden
     controller and readonly behave as `DrawnController` holds them today (`tests/test_ui_look_widgets.py:437-585`);
   - the thread: a value set from a thread that is not Tk's makes no canvas call in that thread, and no renderer or
     image call at all. The next `plot_zctrls` on Tk's thread moves the pointer;
   - pixels: on the PIL face, the cap at the focus is within 3 levels of `KNOB_CAP_HI`, at 0.69 r on the far side
     within 3 of `KNOB_FACE`, the rim ring is `KNOB_EDGE`, and a tick is in `color_hl` at -135 and +135 degrees.
     Another token set moves each.
   Green: the Tk look's module, the tail binding it under `vintage`, and the removals of section 4's stage 1. Pi proof:
   a page of four knobs walked and an encoder turned through 200 values, measuring per-update p99 and face build time
   against the same walk on the base (the renderer path). Screen shots of each kind under stock and vintage, set beside
   the reference picture (section 2).
2. **zynthian-ui: the plugin panel in Tk.** After the current pass. It starts when C2's ctypes door to
   `omx_meter_view_step` and omx-panel's axis in the description exist (section 6, Q6 and Q7); the meter's reading
   goes through that door and the curve's axis is read from the description. Red: for omx-eq8 (curve, bands), omx-geq (bar group) and a metered
   compressor, from recorded `describe` documents (layout and description), the Tk panel makes one item set per
   section, control, bar, curve and meter. A value, a curve's points and a meter's reading move items and make no
   image. Pointer, wheel and keys reach the controls through `zynthian_panel_gestures` (Panel, BarGroup, handle)
   with no renderer call. No module of the panel imports `zynthian_omx_panel_view`'s door or `zynthian_ui_look`. Green:
   the Tk panel; the removals of section 4's stage 2. Pi proof: the drag runs of `docs/blit-per-frame-on-the-pi.md`
   (a bar of omx-geq, a band dot of omx-eq8, at 1024 x 416), against its red line of one display frame (p99 at most
   16.7 ms; the renderer path measured 31 to 50 ms).
3. **zynthian-ui: the door goes.** Red: no file of the tree names `libomx-panel-render`, `zynthian_omx_panel_view`'s
   door or `ZYNTHIAN_OMX_PANEL_RENDER`; the data helpers pass their tests from their new module. Green: the removals of
   section 4's stage 3. Pi proof: a session's walk of the control pages and of a drawn plugin's panel, with
   `libomx-panel-render.so.0` absent from the scratch copy's path, drawn in the look.

## 6. Decided, and the risks left

The owner ruled on 2026-11-20:

- **Q1, the switch: KEPT.** `ZYNTHIAN_UI_LOOK` stays: `stock` is upstream's arc, `vintage` is the Tk drawing.
  Upstream compatibility is kept until the final release.
- **Q2, the knob's shape: Zynthian's own proportions**, checked against a picture (section 2: omx-panel's committed
  MOD GUI vintage shots, or the owner's archive render of omx-strip if handed to the lane). Zynthian never reads
  omx-panel's drawing.
- **Q3, PIL: YES.** Zynthian's toolkit is Tk and PIL; the face is cached per size.
- **Q4, the plugin panel: YES, retired too.** Zynthian draws plugin panels in Tk from the descriptions, which it
  reads as data (`omx-panel describe`, served from the descriptions store), never as pixels. The ctypes door to
  `libomx-panel-render` goes after the Tk version lands (stages 2 and 3).
- **Q5, `libomx-panel-render0` in zynthian-sys's package list: NO.** It is being retired; strips are the interim
  until the Tk plugin panel lands.

The owner's second set of rulings covers stage 2's dependencies. The rule: shared behaviour comes through the C core
and ctypes, never re-implemented in Python, and layout data comes through the description. Stage 2 runs after the
current pass and starts only when both dependencies are met:

- **Q6, the meter's ballistics: stage 2 WAITS** for a ctypes door to omx-dsp's view law, `omx_meter_view_step`
  (omx-panel `docs/behaviour-core.md` section 1). The renderer applies it today: the widget gives it
  `set_meter(value, elapsed)` (`zynthian_widget_omx_panel.py:209-216`). C2, omx-dsp's owner, owns the door, and it
  is requested from C2 directly. No raw-reading meter ships.
- **Q7, the curve's axis: stage 2 WAITS** for omx-panel to publish the axis (log frequency and the others) in the
  description. Today the renderer picks the log-frequency axis from the kind's name (`log_x = strcmp(kind,
  "eq_response") == 0`, omx-panel `renderer/src/view.c:411`, used at `:1028`). Zynthian ships no linear
  placeholder and infers nothing from a kind's name; `view.c:411` is not copied.

Risks:

- Aliased Tk lines and ovals (pointer, pill) next to an anti-aliased PIL face may read as a cheaper finish than the
  console's. Stage 1's shot against the reference picture decides; the fallback is a per-value PIL sprite at today's
  per-value cost.
- The knob grows from 48 to 64 px (renderer) to 168 px (the arc's box), and the value text now sits on the metal cap.
  Its contrast (`color_ctrl_tx` on `KNOB_FACE`) is checked in stage 1.
- The proportions are a copy held to the console only by a picture: they can drift. The picture is named in the
  stage-1 test.
