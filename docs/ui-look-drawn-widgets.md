# The UI look draws the stock controller widgets (zynthian-ui#53, level 2)

Owner, 2026-11-16: the vintage look is one of OpenMixer's main selling points; it should reach
Zynthian's normal screens with a chosen config. Level 1 (zynthian-sys#13, #15; zynthian-webconf#1)
is a colour preset: `config/ui-looks/openmixer-vintage.sh` sets the sixteen `ZYNTHIAN_UI_COLOR_*`,
the font and the main menu grid's six tokens from the console's `tokens.css`, generated, pinned,
never retyped. This note is level 2: `ZYNTHIAN_UI_LOOK` chooses how the stock controller widget is
DRAWN. `stock` is upstream Zynthian's drawing, untouched; `vintage` draws every stock controller
through omx-panel's renderer, the one library every OpenMixer surface draws a panel with
(`libomx-panel-render.so.0`, already behind `zyngine/zynthian_omx_panel_view.py` for the plugin
panels on the Pi). One drawing everywhere: the controller of a synth's page and a knob of an
omx-eq8 panel are the same knob, from the same tokens.

## The switch

- `ZYNTHIAN_UI_LOOK` is read once, by `zyngui/zynthian_gui_config.py`, as `ui_look`. Unset or
  `stock` is `stock`. `vintage` is the drawn look. Any other word is refused by name in the log and
  draws `stock`: the UI starts whatever the config says.
- A look file in zynthian-sys (`config/ui-looks/<look>.sh`) exports `ZYNTHIAN_UI_LOOK` beside its
  colours, so choosing the preset in webconf chooses the drawing too (zynthian-sys: owed, see the
  end). Without it the colours change and the drawing stays stock: level 1 alone.

## Stock is upstream, to the pixel

- `zyngui/zynthian_gui_controller.py`'s class is not edited for this. The module's last lines rebind
  the name `zynthian_gui_controller` to the look's class when `ui_look` is not `stock`; every screen
  that does `from zyngui.zynthian_gui_controller import zynthian_gui_controller` gets that class.
  Under `stock` the name is the class the file defines, the drawn module is never imported, and the
  canvas items the widget creates and configures are the ones upstream creates and configures.
- The drawn class lives in its own module, `zyngui/zynthian_gui_controller_drawn.py`, as a subclass
  made by `drawn_controller(base)`. It overrides only what paints: `show`, `on_size`, `plot_value`,
  `set_title`, `_set_color_graph`, and `zynpot_abs` for the pickup marker's place. Everything else,
  the zynpot, the touch gestures, the value formatting, `calculate_plot_values` (the position law
  included), the MIDI bind text, is upstream's code, inherited, unchanged.
- Upstream compatibility: the fork's path to a PR upstream stays clear. The stock file carries a
  three-line tail and nothing else of this; the drawn widget and the look table are new files.

## What vintage draws, per stock widget

The subclass gives the renderer one panel description per controller, with one section and one
control (the renderer's own grammar: `sections[{key,label}]`, `controls[{symbol,label,section,
standard.widget}]`, as `omx-panel layout` writes it; nothing here invents a field), and paints the
renderer's RGBA over `color_panel_bg` as one canvas image, exactly as `zynthian_widget_omx_panel`
paints a plugin's page. The widget's size is the surface; the renderer scales its face to it.

| stock widget (zctrl) | drawn as | the reading |
|---|---|---|
| a numeric controller (the arc) | `knob`: the renderer's knob, rim, body and pointer over 270 degrees | `set_value(fraction, text)`: `value_plot` and `value_print` as upstream computes them |
| a list of more than two values (ticks/labels) | `selector`: the renderer's selector with the chosen segment lit | `set_choice(at, count, label)` |
| a two-value list (on/off) | `switch`: the renderer's toggle, on from 0.5 | `set_value(index, label)` |
| a path, or a selector counter (no graph) | `display`: the recessed glass with the text in it, no travel drawn | `set_value(0, text)` |
| the label (title) | the renderer's label under the control, `--ink-dim` | `set_title` |
| the value | the renderer's value text, `--ink` on the face | with every `plot_value` |
| the selection (`set_hl`, the arc in `color_hl`) | a 2 px frame around the face in `color_hl`, a canvas rectangle | `_set_color_graph` |
| readonly / disabled (the arc in `color_ctrl_bg_off`) | the same frame in `color_ctrl_bg_off` | `set_color_readonly`, `enable(False)` |
| the MIDI-bind text (`midi_bind`: the CC, `??#??`, X, Y, in `color_ml`/`color_hl`/`color_alt2`) | upstream's own canvas text, left showing and raised above the image: operator state, drawn by the host | `plot_midi_bind`, unchanged |
| the pickup marker (`graph_pickup`: the encoder's place while it has not caught the value) | upstream's own arc, moved onto the renderer's knob: its `target_rect` is the knob's bounding square; the marker is 12 degrees of a circle 2 px outside the rim, the encoder's fraction over the knob's 270 degree travel from the top, in `color_ctrl_tx_off`; a control with no knob (selector, switch, display) shows none; a graph type other than the arc keeps upstream's marker as it is | `zynpot_abs` |
| `hidden=True` | nothing, as upstream: no canvas exists | |

Selection and finish are a host's chrome, not a colour role (omx-panel `schema/look-roles.json`:
"Finish and selection colours ... are a host's chrome and not roles"), so the frame is drawn by
the host, in the colour the stock arc would take. The metal of a knob (the console's `--knob-face`,
`--knob-edge`, the finish blocks of `tokens.css`) is the renderer's to draw: today (omx-panel
0.14, `renderer/src/view.c` `draw_knob`) it draws rim, body and pointer from the roles; a relief
or a glass highlight is one drawing in omx-panel for every surface, never a second one here.

The stock screen's four controllers are four Tk widgets placed by Zynthian's layout
(`zynthian_gui_base`, `ZYNTHIAN_UI_GRAPHIC_LAYOUT`); that placement is not touched, so the
drawn controllers stand where the zynpots say. The owner's drawing rules for repeated groups (an
aligned matrix; HPF and LPF as an EQ's first and last bands) are rules for a panel's layout
(omx-panel's group model, zynthian-ui#54) and bind the plugin panel the renderer draws; a stock
controller is one control and has no group of its own.

## Where each token comes from

The renderer refuses a look short of any role, so the host must value every role. The table is
`zyngine/zynthian_ui_look.py` `tokens(colors, base)`:

- `base` is omx-panel's own `tools/look.json` (the file the renderer reads by default from
  `$ZYNTHIAN_OMX_PANEL_TOOLS`, `/usr/share/omx-panel/tools` on the Pi): every role of
  `schema/look-roles.json` at its default, which is the console's dark theme (`tokens.css` DARK
  block: `--surface #15191e`, `--surface-2 #1c2127`, `--surface-3 #242b33`, `--ink #eaf0f4`, the
  meter zones, the state lamps, the origin marks) with the cyan accent. The role list is read
  from that file, never typed here.
- Over it, the roles Zynthian's palette has a colour for, each from `zynthian_gui_config`'s
  colour the level-1 preset generated from the same console token:

  | role | from | the console token it carries under the vintage preset |
  |---|---|---|
  | `--surface` | `color_panel_bg` | `--surface` #15191e |
  | `--surface-3` | `color_panel_hl` | `--surface-3` #242b33 |
  | `--glass` | `color_off` | `--meter-track` #0d1115 (zynthian-sys's choice for OFF) |
  | `--ink` | `color_tx` | `--ink` #eaf0f4 |
  | `--ink-dim` | `color_tx_off` | `--ink-dim` #8a97a3 |
  | `--legend` | `color_hl` | `--legend` #e9dfc6 |
  | `--accent` | `color_on` | `--accent` #e8732c (orange, the vintage default) |
  | `--state-engaged` | `color_ml` | `--state-engaged` #f2b03a |
  | `--meter-green` | `color_midi` | `--meter-green` #34d17b |
  | `--meter-amber` | `color_alt2` | `--meter-amber` #f2b632 |
  | `--meter-red` | `color_error` | `--danger` #ff5a4d |

  `--surface-2`, `--border`, `--border-strong`, `--ink-faint`, `--state-reduction`,
  `--state-bypass`, the EQ delta pair and the origin marks have no Zynthian colour: they keep the
  base's value, the console's dark theme. The font stays the renderer's (`--font-file`,
  Inter, the family the vintage preset sets as `ZYNTHIAN_UI_FONT_FAMILY`).
- The table is read once per look and tools directory (`look_for` keeps the document, or the
  refusal) so forty controllers do not read forty files. A `look.json` without `tokens`, or short of a
  role the table names, is `LookShort`, named by the role (or "no tokens"); the drawn controller and
  the plugin panel treat it as they treat an absent renderer: stock items (the panel's strips), the
  reason said once, and no view is ever opened in the renderer's own look.
- The host's look reaches the renderer as a data directory of its own: a temporary directory with
  the host's `look.json`, and the renderer's `look/geometry.json`, `fonts/` and `gestures.json`
  linked from the tools directory, given to `omx_panel_view_create_from_files` and removed once the
  view is made (the renderer copies what it reads). The default path, no look, is unchanged.
- The plugin panel (`zynthian_widget_omx_panel`) opens its view with the same look under
  `vintage`; under `stock` it passes none and draws as it does now.

## When the renderer is absent

`vintage` with no renderer (`RendererAbsent`: not installed, or it refused the description), or with
a look the table cannot value (`LookShort`), draws the stock widget and logs the reason once, as the
plugin panel falls back to strips. A renderer that stops (`RendererStopped`) is said once too: the
image and the frame go, the stock items come back, until the controller is built again.

## Held to

`tests/test_ui_look_widgets.py` (42), with real PIL (the Pi has it; CI installs it); the renderer's
view is a stand-in that records the description, the look and the readings and draws a PIL frame:

- the switch: `ui_look` from the environment; unset and `stock` read `stock`; a word that is no
  look is refused by name and reads `stock`;
- stock is upstream: under `stock` the exported class is the file's own class, the drawn module is
  not imported, the canvas holds upstream's five items and no image, and the stock file's class
  names no look, no renderer and no PIL, the module's one tail `if` being the whole change;
- the drawn controller under `vintage`: the overridden set is exactly `show`, `on_size`,
  `plot_value`, `set_title`, `_set_color_graph`, `zynpot_abs`; the description per widget kind
  (knob, selector, switch, display) and the reading each gets; a new value drawn once and an
  unchanged one not at all; the frame on selection, none unselected, `color_ctrl_bg_off` readonly;
  the image equal to the renderer's RGBA composited over `color_panel_bg`, pixel for pixel, the
  graph, label and value hidden; the MIDI-bind text left showing above the image; the pickup
  marker on the knob's target rect at the encoder's angle, gone when the pickup ends, none on a
  control without a knob; a hidden controller draws nothing;
- the look given to the view: every role of the renderer's base, the preset's colours at their
  roles, the others the base's; read once for every controller (the base file gone, the second
  controller still gets it);
- refusals: the renderer absent, a renderer that stops after a draw, a look short of a role, a look
  without tokens: stock items back, no view opened, said once; the same for the plugin panel
  (loaded through `tests/omx_panel_widget_stub.py`, the harness the renderer-crash test shares);
- the look table on its own: roles, a short base refused by name, no tokens refused by name, the
  cache and a cached refusal, `look_for` None under stock and without a tools directory;
- the look's way to the renderer: the look dir carries the host's look and the renderer's geometry,
  font and gestures byte for byte; `View` passes the look (or none) to the renderer's process;
- the fixture `tests/fixtures/omx_panel/look.json` is omx-panel's `tools/look.json` byte for byte
  where `$ZYNTHIAN_OMX_PANEL_TOOLS` names one (CI builds omx-panel at the commit `tests.yml` pins).

Where the renderer is built (CI, the Pi), the pixels themselves are zynthian-ui#74.

## Owed

- Pi screenshots, stock and vintage, of the main menu, a chain and the control screen, with the
  Pi lock: `tools/pi/screenshots.sh` is not written yet; the shots are taken with
  `ssh <pi> 'ZYNTHIAN_UI_LOOK=vintage ...'` and `scrot` on the Pi's display, named in the PR.
- A Fable look review against the console's vintage screens, from those shots.
- zynthian-sys: `config/ui-looks/openmixer-vintage.sh` exports `ZYNTHIAN_UI_LOOK=vintage` and
  `stock.sh` exports `ZYNTHIAN_UI_LOOK=stock` (the pin recomputes; `tests/ui-looks-check.sh` grows
  the key).
- omx-panel#93: the knob's metal and relief, the console's finish, drawn by the renderer.
- omx-panel#94: a face without a head for a one-control description (the controller's cell carries
  the renderer's head today, empty).
- zynthian-ui#74: the vintage controller through the real renderer, a pixel proof in CI and on the Pi.
