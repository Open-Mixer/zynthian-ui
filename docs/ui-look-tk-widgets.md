# The vintage controller drawn with Tk (zynthian-ui#93)

Status: design, not built. Reviewed before any code. It replaces `docs/ui-look-drawn-widgets.md` (zynthian-ui#53,
#74, #79) when its last stage lands.

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
  `_CAP_HI`, `_KNURL`, `_POINTER`, plus the switch track and thumb. Under `stock` they are unset and stock draws
  upstream's arc. No Zynthian file reads omx-panel's `tools/look.json` for the controller.
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
(`value_width = 2 * (radius - arc_width - 1)`, `:240`). The proportions are the console's knob (tick ring at
0.97 to 0.86 of the radius, rim 0.81, knurl 0.73, cap 0.70, pointer 0.21 to 0.63): written in Zynthian's module as its
own drawing of the console's Encoder, checked against a reference picture, not read from omx-panel's file (Q2).

- Layer 1, the face: one PIL `RGBA` image of `2 * radius` square, drawn at 3x and reduced with `LANCZOS`: tick ring
  (11 lines over -135..+135 in `color_hl`, the `--legend` the preset already maps), the shade (a disc offset 1/48 down,
  black at 50 %), the rim (`KNOB_EDGE`), the knurl disc and its 24 lines (`KNOB_KNURL`), the cap: the radial gradient
  approximated by N concentric discs stepping from `KNOB_FACE` (outer) to `KNOB_CAP_HI` (inner), each disc's centre
  moving toward the focus (0.35, 0.3), N = 24 (a step every 0.7 px at 168 px: no visible banding after the
  reduction). Cached by `(2 * radius, tokens)`; shown as one `create_image` under every other item, built at
  `on_size` and never at a value.
- Layer 2, the pointer: three `create_line` items (shaded wall, lit wall, pointer) with `capstyle=ROUND`, moved by
  `coords` at each `plot_value` from the angle `-135 + 270 * value_plot`. A line drawn by Tk is aliased; at 2 to 4 px
  width on a 168 px knob that is acceptable and is the stage-1 look question (Q3). The alternative is a pointer
  rendered into a small rotated PIL sprite per value (one `PhotoImage` per value, the cost today's path pays).
- The value arc: upstream's `graph` arc is not shown (the knob IS the value); the travel ring stays the tick legend.
  A bipolar control (`value_min <= 0 <= value_max`, `plot_value_arc` `:525-526`) shows its zero tick in `color_on`.
- The pickup marker: upstream's `graph_pickup` arc, placed 2 px outside the rim (the tick ring's radius), 12 degrees,
  over the same 270 degrees as the pointer: the code of `place_marker` (`zynthian_gui_controller_drawn.py:191-195`)
  without `target_rect`, the box being the knob's own.
- Selected: the 2 px frame of today (`frame`, `:227-237`), unchanged.

Pure-canvas fallback, no PIL: ovals for shade, rim, knurl disc and 6 to 8 stepped ovals for the cap, 24 + 11 lines.
About 45 items per knob, four knobs a screen: Tk handles that, but every edge is aliased. Kept only as the answer if
the owner refuses PIL for the controller (Q3); PIL is installed on the Pi (`python3-pil`, `python3-pil.imagetk`
11.1.0, measured below) and stock Zynthian already imports it.

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

## 3. The shared-behaviour boundary

What the controller reads from outside Zynthian today, and through what:

| behaviour | read through | by the controller? |
|---|---|---|
| the position law (lin, log, stepped, map) | `zyngine/zynthian_position_law.py:20`, a re-export of `omx_contract.scale` (python3-omx-contract), used in `calculate_plot_values` (`zynthian_gui_controller.py:433-434`) and by the controller's MIDI and nudge paths (`zyngine/zynthian_controller.py:436-440`, `:602-609`, `:686-687`, `:728-730`) for a controller that carries a `position_law` travel (`zynthian_controller.py:89`, `:192-193`, plugin-hostd only) | yes: `value_plot`, the pointer's angle |
| the step | `position_law["step"]`, passed to the renderer by `set_travel` (`zynthian_gui_controller_drawn.py:168-170`) | only to the renderer, which does not move this controller: the gestures are upstream's (`zynthian_gui_controller.py:785-872`). The Tk version passes it nowhere. |
| the gestures | `zyngine/zynthian_panel_gestures.py` reads omx-panel's `schema/gestures.json` (`:5-10`, `table_path` `:43-60`); used by the drawbar (`zynthian_widget_drawbar.py:4`), the XY screen (`zynthian_gui_control_xy.py:33`), the plugin panel (`zynthian_widget_omx_panel.py:31`) | no: the stock controller keeps upstream's drag, wheel and zynpot, and #93 does not change that |
| toggle or list | the engine's word: `is_toggle`, and `toggle_declared` (PR #89, not merged) | yes: the kind (switch or selector) |
| value text | Zynthian's own: `format_print`, `labels`, `get_value2index` (`zynthian_gui_controller.py:410-464`) | yes, as upstream |

The design keeps that boundary exactly: the Tk controller reads `value_plot` and `value_print` as upstream computes
them, and the kind from the engine's word. It proposes nothing new in omx-panel. When omx-panel's behaviour core lands
(its `docs/behaviour-core.md` section 7, step 4: `zynthian_panel_gestures.py` and `zynthian_position_law.py` become
an adapter over `python3-omx-panel-behaviour`), the controller's `value_plot` and value text move to that adapter in
that step's own lane, not in #93.

One finding on the boundary: two classifiers of a controller's kind exist. `widget_kind` says "two ticks is a switch"
(`zynthian_gui_controller_drawn.py:55`) while `zynthian_panel_gestures.widget_of` says "`is_toggle` is a switch, ticks
a selector" (`zyngine/zynthian_panel_gestures.py:662-666`). Upstream sets `is_toggle` from two labels too, which is
why #89 adds `toggle_declared`. The Tk version takes ONE function for both (stage 1), so the drawing and the gesture
table cannot disagree on a control.

## 4. What is removed when the Tk version lands, and what stays

### Removed (the controller's image path)

- `zyngui/zynthian_gui_controller_drawn.py`: its renderer calls, `View`, `description`, `open_view`, `give_reading`,
  `paint`, `show_image`'s RGBA composite, `fall_back` on `RendererAbsent`/`RendererStopped`/`LookShort`, the
  `after_idle` thread hop for renderer calls (`:124-129`, `:116-120`; Tk items are configured from the CUIA thread
  as the stock widget already does). The module is replaced by the Tk look's module (name in stage 1); `widget_kind`,
  `frame` and the marker's arithmetic move into it.
- The controller's use of the ctypes door: `from zyngine import zynthian_omx_panel_view` in the controller
  (`zynthian_gui_controller_drawn.py:39`). The door itself stays (below).
- The controller's use of `zynthian_ui_look` (`zynthian_gui_controller_drawn.py:40`, `:164`, `:171`): the controller
  takes its tokens from `zynthian_gui_config`, as the grid does.
- `vintage` meaning "drawn by omx-panel's renderer" in `zynthian_gui_config.py:565-568` and in its log line ("the
  controllers are drawn stock"). Whether the `stock`/`vintage` switch itself goes is Q1.
- Tests: in `tests/test_ui_look_widgets.py` the classes `DrawnController` (`:348-585`), `RealRenderer` (the pixel tests
  of zynthian-ui#74, `:587-661`) and `WhatCIMustHave`'s renderer rows (`:333-346`); in
  `tests/test_omx_panel_renderer_race.py` the controller rows (`ControllerHarness`, `TheLookAfterAStop`,
  `TheRendererIsTksThreads`, `:250-421`); PR #89's `tests/test_controller_toggle_declared.py` keeps its controller
  half (the engine's word on `zynthian_controller`) and its drawn-widget half moves to the Tk test. They are replaced,
  stage by stage, by the Tk tests of section 5.
- CI: `.github/workflows/tests.yml:132-133` (the skip guard of the drawn-controller tests: "no PIL|no omx-panel tools
  directory") is rewritten for the Tk tests; `tools/restated_declarations.py:97` drops
  `zyngui/zynthian_gui_controller_drawn.py`.
- Docs: `docs/ui-look-drawn-widgets.md` is deleted; this note becomes the look's note (its section 1 rewritten as
  "what it draws").

### Not removed by #93, and why

- `zyngine/zynthian_omx_panel_view.py` (the ctypes door to `libomx-panel-render.so.0`, `:41`) stays: the plugin panel
  draws through it (`zyngui/zynthian_widget_omx_panel.py:30`, `View` `:155`, `PanelImage` `:225`, the input events
  `:229-292`), and the plugin-hostd engine uses its non-drawing helpers (`zyngine/zynthian_engine_plugin_hostd.py:39`:
  `output_set` `:212`, `drawn_parts` `:1382`, `curve_bind_line` `:1394`, `curve_points` `:1402`). omx-panel's own
  spec keeps the plugin panels on its renderer "until it draws them itself" (`behaviour-core.md:26`). Whether the
  owner's rule reaches the plugin panel is Q4; #93 does not touch it.
- `zyngine/zynthian_ui_look.py` stays while the plugin panel wears the look (`zynthian_widget_omx_panel.py:154-155`),
  with its tests (`PanelOverAShortLook`, `LookBaseFixture`, `LookTable`, `PanelWearsTheLook`, `LookDir`,
  `tests/test_ui_look_widgets.py:663-800`), moved to a panel test file. PR #88 (`cpu_colour`) also lands there.
- The renderer's tests that are the panel's: `tests/test_omx_panel_view.py`, `test_omx_panel_renderer_crash.py`,
  `test_omx_panel_dirty_blit.py`, `test_plugin_hostd_drawn.py`, `test_control_blank_slot_panel.py`, the panel rows of
  `test_omx_panel_renderer_race.py`, and the CI step that builds the renderer (`tests.yml:91-109`).
- Packaging: zynthian-ui has no `debian/` and no install recipe of its own. zynthian-sys installs `omx-panel` and
  `python3-omx-contract` (`config/openmixer-packages`); omx-panel stays needed (its `schema/gestures.json`, `describe`,
  `omx-modgui-sync`). Nothing to remove for #93. Finding: `libomx-panel-render0` is not in that list and nothing
  depends on it (omx-panel `debian/control:41-45`: it depends on `omx-panel`, not the reverse); the Pi has 0.13.8
  installed (queried 2026-11-20), so a fresh image would draw every plugin panel as strips. That is the panel's
  packaging question, raised here, not fixed here.
- The users of the image path that are not the controller, found by grep: the plugin panel widget and its tests above;
  `tools/pi/drawn_panel_on_the_pi.py`, `tools/pi/blit_per_frame_on_the_pi.py`, `tools/pi/pages_on_the_pi.py` (Pi
  tools of the panel); `docs/blit-per-frame-on-the-pi.md`.

## 5. Staged lanes

Each stage: one PR on `openmixer`, the red commit first (tests that fail on the base), then the green; the failing
line and the run in the PR body. Tests run in CI without a display: the canvas is the recording stand-in the look
tests already use (`tests/test_ui_look_widgets.py` `Canvas`, `:94`), the PIL images are real (CI installs
`python3-pil`). Pi proofs run under the Pi evidence runner (`pi-evidence.sh <label> <cmd>`), one at a time, in its
scratch dir, never touching the running UI.

0. **zynthian-sys: the knob tokens.** Red: `tests/ui-looks-check.sh` asks for `ZYNTHIAN_UI_COLOR_KNOB_FACE`, `_EDGE`,
   `_CAP_HI`, `_KNURL`, `_POINTER`, `_SWITCH_TRACK`, `_SWITCH_THUMB` in the vintage preset, valued from the console's
   pinned `tokens.css` (aluminium finish). Green: the generator emits them; the pin recomputes. zynthian-ui reads them
   in `zynthian_gui_config` with upstream-neutral defaults (unset under stock).
1. **The knob.** Red: a structure test (the controller under the Tk look creates one face image and three pointer
   lines; a new value moves the pointer's `coords` to `-135 + 270 * value_plot` and creates no image; the face is built
   once per size and token set; the stock graph arc is hidden, title, value, MIDI bind and pickup marker shown above
   the face) and a pixel test on the PIL face (at the centre's focus the cap is within 3 levels of `KNOB_CAP_HI`, at
   0.69 r on the far side within 3 of `KNOB_FACE`, the rim ring `KNOB_EDGE`, a tick in `color_hl` at -135 and +135
   degrees; another token set moves each). Plus the one-classifier test (section 3). Green: the module, the face
   builder, the knob. Pi proof: a page of four knobs walked and an encoder turned through 200 values: per-update p99
   and the face build time, against the same walk on the base (the renderer path), and a screen shot of both.
2. **Switch, selector, display.** Red: per kind, the items created, the value change moving items and creating no
   image, the colours from the tokens, a `toggle_declared: False` two-value list drawn as a selector. Green: the three
   kinds. Pi proof: shots of a page with each kind (stock and vintage).
3. **The marker, the frame, blank slots, hidden controllers, readonly.** Red: the existing behaviours of
   `DrawnController` (`tests/test_ui_look_widgets.py:437-585`) restated against the Tk items. Green: the module.
4. **The cut-over.** Red: a test that the controller under the look imports neither `zynthian_omx_panel_view` nor
   `zynthian_ui_look`, makes no renderer call with the renderer absent, and that no file but the panel's names
   `zynthian_gui_controller_drawn`. Green: the tail of `zynthian_gui_controller.py` binds the Tk class; the drawn
   module, its tests and its CI guard are deleted (section 4); `docs/ui-look-drawn-widgets.md` deleted. Pi proof: a
   session's walk of the control pages under the vintage preset with the renderer library moved out of the path in a
   scratch copy: the controllers are drawn in the look (the panel draws strips, as designed).

## 6. Risks and open questions for the owner

Risks:

- Aliased Tk lines and ovals (pointer, pill) next to an anti-aliased PIL face may read as a cheaper finish than the
  console's. Stage 1's shot decides; the fallback is a per-value PIL sprite at today's per-value cost.
- The knob grows from 48 to 64 px (renderer) to 168 px (the arc's box): the face is a larger, better-lit object, and
  the value text now sits on the metal cap; its contrast (`color_ctrl_tx` on `KNOB_FACE`) must be checked in stage 1.
- Writing the console's knob proportions into Zynthian is a copy of a drawing, held to the console only by a
  reference picture: it can drift (Q2).

Questions:

- **Q1. The switch.** The brief lists the stock/vintage option as removed. Read in the code, removing it either makes
  the Tk vintage drawing the only controller (upstream's arc gone from the fork, `StockIsUpstream` and the upstream
  PR path gone), or makes "vintage" follow from the colour preset alone. Recommendation: keep ONE switch,
  `ZYNTHIAN_UI_LOOK` (`stock` = upstream's arc to the pixel, `vintage` = Zynthian's Tk drawing), since zynthian-sys's
  look files already export it; remove only the renderer meaning.
- **Q2. Where the knob's shape comes from.** Zynthian's own proportions checked by picture (this design), or Zynthian
  reading the declarative `drawings.knob-vintage` of omx-panel's `tools/look.json` (data, not pixels, but a look file
  the behaviour core says stays with omx-panel's drawing)? The design assumes the former.
- **Q3. PIL for the face.** Allowed (as the grid, mixer and meters already do), or canvas items only?
- **Q4. The plugin panel.** Does the rule "each toolkit draws its own" also retire `zynthian_widget_omx_panel`'s
  renderer path (bars, curves, meters), now or after the behaviour core? #93 assumes not.
- **Q5.** `libomx-panel-render0` is not installed by zynthian-sys's package list: add it, or let it go with Q4?
