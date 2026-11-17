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
  `set_title`, `_set_color_graph`. Everything else, the zynpot, the touch gestures, the value
  formatting, `calculate_plot_values` (the position law included), the MIDI bind text, is upstream's
  code, inherited, unchanged.
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
- The host's look reaches the renderer as a data directory of its own: a temporary directory with
  the host's `look.json`, and the renderer's `look/geometry.json`, `fonts/` and `gestures.json`
  linked from the tools directory, given to `omx_panel_view_create_from_files` and removed once the
  view is made (the renderer copies what it reads). The default path, no look, is unchanged.
- The plugin panel (`zynthian_widget_omx_panel`) opens its view with the same look under
  `vintage`; under `stock` it passes none and draws as it does now.

## When the renderer is absent

`vintage` with no renderer (`RendererAbsent`: not installed, or it refused the description) draws
the stock widget and logs the reason once, as the plugin panel falls back to strips. A renderer
that stops (`RendererStopped`) is said once too; the controller draws stock until it is built
again.

## Held to

`tests/test_ui_look_widgets.py`, with real PIL (the Pi has it; CI installs it):

- the switch: `ui_look` from the environment; unset and `stock` read `stock`; a word that is no
  look is refused by name and reads `stock`;
- stock is upstream: under `stock` the exported class is the file's own class, the drawn module is
  not imported, and the stock file names no look, no renderer and no PIL;
- the drawn controller under `vintage`: the description per widget kind (knob, selector, switch,
  display), the values and labels given to the view, the frame on selection, the look given to the
  view carrying the preset's colours at their roles, and the image on the canvas equal to the
  renderer's RGBA composited over `color_panel_bg` (PIL, pixel for pixel);
- the look table: every role of the base is present, the palette's roles carry the config's
  colours, the others the base's; a base short of a role the table names is refused by name;
- the renderer's fallback: `RendererAbsent` draws stock and says so once.

Where the renderer is built (CI, the Pi), `tests/test_omx_panel_view.py`'s pattern draws a knob
through the real library and reads the accent at the pointer.

## Owed

- Pi screenshots, stock and vintage, of the main menu, a chain and the control screen, with the
  Pi lock: `tools/pi/screenshots.sh` is not written yet; the shots are taken with
  `ssh <pi> 'ZYNTHIAN_UI_LOOK=vintage ...'` and `scrot` on the Pi's display, named in the PR.
- A Fable look review against the console's vintage screens, from those shots.
- zynthian-sys: `config/ui-looks/openmixer-vintage.sh` exports `ZYNTHIAN_UI_LOOK=vintage` and
  `stock.sh` exports `ZYNTHIAN_UI_LOOK=stock` (the pin recomputes; `tests/ui-looks-check.sh` grows
  the key).
- omx-panel: the knob's metal and relief, and a face without a head for a one-control panel (the
  controller's cell carries the renderer's head today, empty).
