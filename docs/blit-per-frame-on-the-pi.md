# One drag frame of a drawn panel on the Pi (zynthian-ui#44)

Measured on 2026-11-16 on the Raspberry Pi 5 (Zynthian, 1024 x 768 screen, the UI running beside it) with
`tools/pi/blit_per_frame_on_the_pi.py`. The panel view and widget code is 97e896ab (the renderer in a process of its
own); the script is 16b378af with the two edits committed beside this note (the view module loaded by its path, and
`ORDER`). The renderer is the Pi's libomx-panel-render0 0.13.7.

Each frame does what the panel widget does on a drag: the event to the renderer (input), its draw, the RGBA to Tk
image conversion over the background (convert), and the canvas update (canvas). Frames run back to back for 30 s per
drag, so fps is what the screen reached. Times are in ms, p50 / p99 / max. **Red: a p99 frame above one display frame,
16.7 ms at 60 Hz.**

| run | size | drag | where the renderer runs | fps | input | draw | convert | canvas | frame |
|---|---|---|---|---|---|---|---|---|---|
| A (isolated first) | 1024x416 | bar | renderer process | 32.0 | 0.43 / 0.75 / 1.48 | 16.84 / 17.86 / 23.77 | 5.47 / 6.36 / 10.65 | 8.32 / 9.87 / 14.55 | **31.06 / 33.36 / 38.72** |
| A (isolated first) | 1024x416 | band dot | renderer process | 34.3 | 0.43 / 0.76 / 2.41 | 13.74 / 15.15 / 23.88 | 4.91 / 6.43 / 15.82 | 9.63 / 11.59 / 54.79 | **28.87 / 31.67 / 92.81** |
| A (isolated first) | 1024x416 | bar | in the UI's process | 27.7 | 0.12 / 0.25 / 0.95 | 15.71 / 24.94 / 31.72 | 5.38 / 9.47 / 24.72 | 10.8 / 18.26 / 53.07 | **31.97 / 51.51 / 89.33** |
| A (isolated first) | 1024x416 | band dot | in the UI's process | 21.2 | 0.13 / 1.41 / 3.59 | 19.84 / 21.46 / 28.91 | 7.08 / 13.21 / 29.97 | 18.25 / 58.49 / 175.29 | **45.18 / 89.36 / 205.21** |
| B (isolated first) | 1024x768 | bar | renderer process | 18.0 | 0.52 / 0.85 / 3.56 | 27.61 / 28.64 / 53.27 | 12.49 / 13.31 / 25.92 | 14.42 / 15.61 / 47.08 | **55.15 / 68.61 / 88.91** |
| B (isolated first) | 1024x768 | band dot | renderer process | 19.8 | 0.52 / 0.87 / 2.14 | 22.7 / 23.91 / 35.2 | 11.32 / 13.15 / 29.92 | 15.6 / 16.75 / 39.33 | **50.3 / 55.15 / 104.95** |
| B (isolated first) | 1024x768 | bar | in the UI's process | 4.2 | 0.14 / 12.15 / 15.19 | 26.17 / 40.53 / 44.64 | 12.78 / 325.96 / 495.73 | 17.41 / 7201.89 / 7832.02 | **56.5 / 7574.13 / 8368.62** |
| B (isolated first) | 1024x768 | band dot | in the UI's process | 0.1 | 122.45 / 122.45 / 122.45 | 26.26 / 26.26 / 26.26 | 440.44 / 440.44 / 440.44 | 31839.87 / 31839.87 / 31839.87 | **32429.02 / 32429.02 / 32429.02** |
| C (in-process first) | 1024x416 | bar | in the UI's process | 22.5 | 0.14 / 0.31 / 1.15 | 24.37 / 24.86 / 24.92 | 7.8 / 8.1 / 23.06 | 12.1 / 12.91 / 15.84 | **44.47 / 45.49 / 60.23** |
| C (in-process first) | 1024x416 | band dot | in the UI's process | 24.9 | 0.14 / 0.29 / 1.31 | 19.71 / 20.05 / 20.52 | 6.7 / 7.0 / 66.29 | 13.58 / 14.44 / 14.68 | **40.11 / 41.24 / 101.74** |
| C (in-process first) | 1024x416 | bar | renderer process | 20.3 | 0.52 / 0.86 / 1.51 | 25.54 / 25.96 / 37.14 | 8.05 / 8.36 / 8.48 | 14.99 / 15.66 / 15.86 | **49.12 / 50.07 / 61.79** |
| C (in-process first) | 1024x416 | band dot | renderer process | 22.4 | 0.52 / 0.86 / 1.59 | 20.72 / 21.12 / 57.86 | 6.99 / 7.24 / 7.33 | 16.33 / 17.23 / 18.06 | **44.6 / 45.64 / 84.38** |

## What the figures say

- **Every run is red.** At 1024 x 416 a drag frame's p99 is 31 to 50 ms in seven of the eight rows (89 ms in run
  A's in-process band dot); at the whole 1024 x 768 screen, 55 to 69 ms in the renderer's process. The screen reached
  20 to 34 fps at 1024 x 416.
- **The renderer's draw is the largest part:** 14 to 25 ms at 1024 x 416, alone above one display frame. The canvas
  update (8 to 17 ms) and the conversion (5 to 8 ms) follow. None of these is the process boundary.
- **The process boundary costs about 0.4 ms per input** (p50 0.43 to 0.52 ms isolated against 0.12 to 0.14 ms in the
  UI's process). The draw includes the copy out of shared memory, and its gap between modes is within the drift of
  the same mode between runs: the bar's isolated draw is 16.8 ms in run A and 25.5 ms in run C.
- **Run B's in-process rows are not a figure of the in-process view.** They ran last, after a minute of full-screen
  frames, with the Pi's load at 6, and the canvas update took up to 32 s. Run C puts in-process first, and those rows
  are in line with the isolated ones. They are kept above because they were measured.

So isolating the renderer (#44 part 1) does not move the frame. Bringing a drag under one display frame needs a
cheaper draw (only the region that moved) and a cheaper path to the screen than a full Tk PhotoImage per frame. That
is new work, and a reason to file an issue, not part of #44.

## The measured lines

- run A: `{"drag": "bar", "plugin": "omx-geq", "control": "band08", "size": "1024x416", "frames": 961, "fps": 32.0, "input": {"p50": 0.43, "p99": 0.75, "max": 1.48}, "draw": {"p50": 16.84, "p99": 17.86, "max": 23.77}, "convert": {"p50": 5.47, "p99": 6.36, "max": 10.65}, "canvas": {"p50": 8.32, "p99": 9.87, "max": 14.55}, "frame": {"p50": 31.06, "p99": 33.36, "max": 38.72}, "red": true, "where": "renderer process", "commit": ""}`
- run A: `{"drag": "band dot", "plugin": "omx-eq8", "control": "b3_freq", "size": "1024x416", "frames": 1029, "fps": 34.3, "input": {"p50": 0.43, "p99": 0.76, "max": 2.41}, "draw": {"p50": 13.74, "p99": 15.15, "max": 23.88}, "convert": {"p50": 4.91, "p99": 6.43, "max": 15.82}, "canvas": {"p50": 9.63, "p99": 11.59, "max": 54.79}, "frame": {"p50": 28.87, "p99": 31.67, "max": 92.81}, "red": true, "where": "renderer process", "commit": ""}`
- run A: `{"drag": "bar", "plugin": "omx-geq", "control": "band08", "size": "1024x416", "frames": 832, "fps": 27.7, "input": {"p50": 0.12, "p99": 0.25, "max": 0.95}, "draw": {"p50": 15.71, "p99": 24.94, "max": 31.72}, "convert": {"p50": 5.38, "p99": 9.47, "max": 24.72}, "canvas": {"p50": 10.8, "p99": 18.26, "max": 53.07}, "frame": {"p50": 31.97, "p99": 51.51, "max": 89.33}, "red": true, "where": "in the UI's process", "commit": ""}`
- run A: `{"drag": "band dot", "plugin": "omx-eq8", "control": "b3_freq", "size": "1024x416", "frames": 637, "fps": 21.2, "input": {"p50": 0.13, "p99": 1.41, "max": 3.59}, "draw": {"p50": 19.84, "p99": 21.46, "max": 28.91}, "convert": {"p50": 7.08, "p99": 13.21, "max": 29.97}, "canvas": {"p50": 18.25, "p99": 58.49, "max": 175.29}, "frame": {"p50": 45.18, "p99": 89.36, "max": 205.21}, "red": true, "where": "in the UI's process", "commit": ""}`
- run B: `{"drag": "bar", "plugin": "omx-geq", "control": "band08", "size": "1024x768", "frames": 542, "fps": 18.0, "input": {"p50": 0.52, "p99": 0.85, "max": 3.56}, "draw": {"p50": 27.61, "p99": 28.64, "max": 53.27}, "convert": {"p50": 12.49, "p99": 13.31, "max": 25.92}, "canvas": {"p50": 14.42, "p99": 15.61, "max": 47.08}, "frame": {"p50": 55.15, "p99": 68.61, "max": 88.91}, "red": true, "where": "renderer process", "commit": ""}`
- run B: `{"drag": "band dot", "plugin": "omx-eq8", "control": "b3_freq", "size": "1024x768", "frames": 594, "fps": 19.8, "input": {"p50": 0.52, "p99": 0.87, "max": 2.14}, "draw": {"p50": 22.7, "p99": 23.91, "max": 35.2}, "convert": {"p50": 11.32, "p99": 13.15, "max": 29.92}, "canvas": {"p50": 15.6, "p99": 16.75, "max": 39.33}, "frame": {"p50": 50.3, "p99": 55.15, "max": 104.95}, "red": true, "where": "renderer process", "commit": ""}`
- run B: `{"drag": "bar", "plugin": "omx-geq", "control": "band08", "size": "1024x768", "frames": 130, "fps": 4.2, "input": {"p50": 0.14, "p99": 12.15, "max": 15.19}, "draw": {"p50": 26.17, "p99": 40.53, "max": 44.64}, "convert": {"p50": 12.78, "p99": 325.96, "max": 495.73}, "canvas": {"p50": 17.41, "p99": 7201.89, "max": 7832.02}, "frame": {"p50": 56.5, "p99": 7574.13, "max": 8368.62}, "red": true, "where": "in the UI's process", "commit": ""}`
- run B: `{"drag": "band dot", "plugin": "omx-eq8", "control": "b3_freq", "size": "1024x768", "frames": 2, "fps": 0.1, "input": {"p50": 122.45, "p99": 122.45, "max": 122.45}, "draw": {"p50": 26.26, "p99": 26.26, "max": 26.26}, "convert": {"p50": 440.44, "p99": 440.44, "max": 440.44}, "canvas": {"p50": 31839.87, "p99": 31839.87, "max": 31839.87}, "frame": {"p50": 32429.02, "p99": 32429.02, "max": 32429.02}, "red": true, "where": "in the UI's process", "commit": ""}`
- run C: `{"drag": "bar", "plugin": "omx-geq", "control": "band08", "size": "1024x416", "frames": 675, "fps": 22.5, "input": {"p50": 0.14, "p99": 0.31, "max": 1.15}, "draw": {"p50": 24.37, "p99": 24.86, "max": 24.92}, "convert": {"p50": 7.8, "p99": 8.1, "max": 23.06}, "canvas": {"p50": 12.1, "p99": 12.91, "max": 15.84}, "frame": {"p50": 44.47, "p99": 45.49, "max": 60.23}, "red": true, "where": "in the UI's process", "commit": ""}`
- run C: `{"drag": "band dot", "plugin": "omx-eq8", "control": "b3_freq", "size": "1024x416", "frames": 746, "fps": 24.9, "input": {"p50": 0.14, "p99": 0.29, "max": 1.31}, "draw": {"p50": 19.71, "p99": 20.05, "max": 20.52}, "convert": {"p50": 6.7, "p99": 7.0, "max": 66.29}, "canvas": {"p50": 13.58, "p99": 14.44, "max": 14.68}, "frame": {"p50": 40.11, "p99": 41.24, "max": 101.74}, "red": true, "where": "in the UI's process", "commit": ""}`
- run C: `{"drag": "bar", "plugin": "omx-geq", "control": "band08", "size": "1024x416", "frames": 611, "fps": 20.3, "input": {"p50": 0.52, "p99": 0.86, "max": 1.51}, "draw": {"p50": 25.54, "p99": 25.96, "max": 37.14}, "convert": {"p50": 8.05, "p99": 8.36, "max": 8.48}, "canvas": {"p50": 14.99, "p99": 15.66, "max": 15.86}, "frame": {"p50": 49.12, "p99": 50.07, "max": 61.79}, "red": true, "where": "renderer process", "commit": ""}`
- run C: `{"drag": "band dot", "plugin": "omx-eq8", "control": "b3_freq", "size": "1024x416", "frames": 672, "fps": 22.4, "input": {"p50": 0.52, "p99": 0.86, "max": 1.59}, "draw": {"p50": 20.72, "p99": 21.12, "max": 57.86}, "convert": {"p50": 6.99, "p99": 7.24, "max": 7.33}, "canvas": {"p50": 16.33, "p99": 17.23, "max": 18.06}, "frame": {"p50": 44.6, "p99": 45.64, "max": 84.38}, "red": true, "where": "renderer process", "commit": ""}`

## After #59's zynthian-ui half: only the changed rows blitted (2026-11-16, b8aa4422)

**Correction to the table above:** the bar rows (omx-geq band08) were a sideways drag on a vertical bar, so the bar
never moved and each frame drew and blitted the same panel. Their draw, conversion and canvas times are a whole-panel
frame's, which is what that table measures, but they are not a moving bar. The script now drags vertically, as the
gestures declare for a bar and a dot alike, and records the rows blitted per frame.

The code is b8aa4422 (PanelImage: one kept Tk photo, only the rows a draw changed converted and copied into it), the
renderer the Pi's 0.13.7, 30 s per drag at 1024 x 416, the vertical drag (run D).

| run | drag | where the renderer runs | fps | input | draw | blit | canvas | frame | rows blitted |
|---|---|---|---|---|---|---|---|---|---|
| D | bar | renderer process | 29.9 | 0.39 / 0.59 / 1.33 | 25.02 / 25.44 / 37.62 | 8.75 / 9.03 / 96.14 | 0.46 / 1.32 / 1.65 | **34.63 / 35.7 / 125.44** | 11 / 21 / 416 |
| D | band dot | renderer process | 33.5 | 0.39 / 0.61 / 2.32 | 20.17 / 20.66 / 39.22 | 8.77 / 9.04 / 19.12 | 0.45 / 0.69 / 4.85 | **29.8 / 30.57 / 54.86** | 12 / 23 / 416 |
| D | bar | in the UI's process | 31.0 | 0.11 / 0.19 / 0.46 | 24.04 / 24.5 / 31.29 | 8.81 / 9.08 / 27.43 | 0.45 / 1.31 / 3.0 | **33.42 / 34.53 / 52.29** | 11 / 21 / 416 |
| D | band dot | in the UI's process | 34.7 | 0.11 / 0.21 / 0.55 | 19.24 / 19.64 / 26.11 | 8.95 / 10.5 / 31.26 | 0.45 / 0.75 / 1.88 | **28.79 / 33.01 / 50.92** | 12 / 23 / 416 |

- **Still red:** the p99 frame is 30.6 to 35.7 ms against 16.7 ms.
- **The canvas update fell from 8 to 17 ms to about 0.45 ms.** Tk redraws only the copied rows of the one kept photo.
- **The blit is about 8.8 ms for 11 or 12 rows.** That is too much for 12 x 1024 pixels: on x86 under Xvfb, a new
  photo per region costs 0.64 ms and a PPM `put` 0.32 ms. Where the 8.8 ms goes on the Pi (the compare, the
  composite, the photo) is the next thing to measure, split by step.
- **The renderer's whole-panel draw is 19 to 25 ms, unchanged, and is the larger part.** The budget goes green only
  with Open-Mixer/omx-panel#78 (a draw of the changed regions only).
- Runs taken before the drag direction was fixed are kept as measured lines below. Their band-dot rows are valid;
  their bar rows moved nothing, and one in-process band-dot run collapsed (canvas up to 6.3 s) when it ran second.

## The measured lines (#59)

- D (vertical drag): `{"drag": "bar", "plugin": "omx-geq", "control": "band08", "size": "1024x416", "frames": 897, "fps": 29.9, "input": {"p50": 0.39, "p99": 0.59, "max": 1.33}, "draw": {"p50": 25.02, "p99": 25.44, "max": 37.62}, "blit": {"p50": 8.75, "p99": 9.03, "max": 96.14}, "canvas": {"p50": 0.46, "p99": 1.32, "max": 1.65}, "frame": {"p50": 34.63, "p99": 35.7, "max": 125.44}, "rows blitted": {"p50": 11, "p99": 21, "max": 416}, "red": true, "where": "renderer process", "commit": ""}`
- D (vertical drag): `{"drag": "band dot", "plugin": "omx-eq8", "control": "b3_freq", "size": "1024x416", "frames": 1005, "fps": 33.5, "input": {"p50": 0.39, "p99": 0.61, "max": 2.32}, "draw": {"p50": 20.17, "p99": 20.66, "max": 39.22}, "blit": {"p50": 8.77, "p99": 9.04, "max": 19.12}, "canvas": {"p50": 0.45, "p99": 0.69, "max": 4.85}, "frame": {"p50": 29.8, "p99": 30.57, "max": 54.86}, "rows blitted": {"p50": 12, "p99": 23, "max": 416}, "red": true, "where": "renderer process", "commit": ""}`
- D (vertical drag): `{"drag": "bar", "plugin": "omx-geq", "control": "band08", "size": "1024x416", "frames": 930, "fps": 31.0, "input": {"p50": 0.11, "p99": 0.19, "max": 0.46}, "draw": {"p50": 24.04, "p99": 24.5, "max": 31.29}, "blit": {"p50": 8.81, "p99": 9.08, "max": 27.43}, "canvas": {"p50": 0.45, "p99": 1.31, "max": 3.0}, "frame": {"p50": 33.42, "p99": 34.53, "max": 52.29}, "rows blitted": {"p50": 11, "p99": 21, "max": 416}, "red": true, "where": "in the UI's process", "commit": ""}`
- D (vertical drag): `{"drag": "band dot", "plugin": "omx-eq8", "control": "b3_freq", "size": "1024x416", "frames": 1041, "fps": 34.7, "input": {"p50": 0.11, "p99": 0.21, "max": 0.55}, "draw": {"p50": 19.24, "p99": 19.64, "max": 26.11}, "blit": {"p50": 8.95, "p99": 10.5, "max": 31.26}, "canvas": {"p50": 0.45, "p99": 0.75, "max": 1.88}, "frame": {"p50": 28.79, "p99": 33.01, "max": 50.92}, "rows blitted": {"p50": 12, "p99": 23, "max": 416}, "red": true, "where": "in the UI's process", "commit": ""}`
- sideways bar, isolated first: `{"drag": "bar", "plugin": "omx-geq", "control": "band08", "size": "1024x416", "frames": 1148, "fps": 38.3, "input": {"p50": 0.34, "p99": 0.57, "max": 5.37}, "draw": {"p50": 24.98, "p99": 25.4, "max": 37.66}, "blit": {"p50": 0.53, "p99": 0.78, "max": 71.1}, "canvas": {"p50": 0.18, "p99": 0.34, "max": 1.34}, "frame": {"p50": 26.04, "p99": 26.51, "max": 99.38}, "rows blitted": {"p50": 0, "p99": 0, "max": 416}, "red": true, "where": "renderer process", "commit": ""}`
- sideways bar, isolated first: `{"drag": "band dot", "plugin": "omx-eq8", "control": "b3_freq", "size": "1024x416", "frames": 1005, "fps": 33.5, "input": {"p50": 0.39, "p99": 0.6, "max": 1.34}, "draw": {"p50": 20.11, "p99": 20.49, "max": 26.07}, "blit": {"p50": 8.89, "p99": 9.08, "max": 19.57}, "canvas": {"p50": 0.47, "p99": 0.74, "max": 2.52}, "frame": {"p50": 29.88, "p99": 30.37, "max": 43.14}, "rows blitted": {"p50": 12, "p99": 23, "max": 416}, "red": true, "where": "renderer process", "commit": ""}`
- sideways bar, isolated first: `{"drag": "bar", "plugin": "omx-geq", "control": "band08", "size": "1024x416", "frames": 1192, "fps": 39.7, "input": {"p50": 0.09, "p99": 0.24, "max": 4.98}, "draw": {"p50": 24.07, "p99": 26.01, "max": 50.4}, "blit": {"p50": 0.64, "p99": 1.41, "max": 20.28}, "canvas": {"p50": 0.19, "p99": 0.85, "max": 12.38}, "frame": {"p50": 24.99, "p99": 29.14, "max": 53.18}, "rows blitted": {"p50": 0, "p99": 0, "max": 416}, "red": true, "where": "in the UI's process", "commit": ""}`
- sideways bar, isolated first: `{"drag": "band dot", "plugin": "omx-eq8", "control": "b3_freq", "size": "1024x416", "frames": 125, "fps": 3.5, "input": {"p50": 0.12, "p99": 36.46, "max": 39.02}, "draw": {"p50": 19.86, "p99": 82.1, "max": 159.5}, "blit": {"p50": 9.23, "p99": 579.45, "max": 1831.06}, "canvas": {"p50": 0.54, "p99": 5226.9, "max": 6339.95}, "frame": {"p50": 29.86, "p99": 6984.98, "max": 7256.49}, "rows blitted": {"p50": 12, "p99": 32, "max": 416}, "red": true, "where": "in the UI's process", "commit": ""}`
- sideways bar, in-process first: `{"drag": "bar", "plugin": "omx-geq", "control": "band08", "size": "1024x416", "frames": 1198, "fps": 39.9, "input": {"p50": 0.09, "p99": 0.17, "max": 0.84}, "draw": {"p50": 23.99, "p99": 24.44, "max": 25.97}, "blit": {"p50": 0.63, "p99": 0.85, "max": 147.09}, "canvas": {"p50": 0.19, "p99": 0.34, "max": 1.45}, "frame": {"p50": 24.92, "p99": 25.35, "max": 173.0}, "rows blitted": {"p50": 0, "p99": 0, "max": 416}, "red": true, "where": "in the UI's process", "commit": ""}`
- sideways bar, in-process first: `{"drag": "band dot", "plugin": "omx-eq8", "control": "b3_freq", "size": "1024x416", "frames": 1041, "fps": 34.7, "input": {"p50": 0.11, "p99": 0.2, "max": 0.57}, "draw": {"p50": 19.22, "p99": 19.57, "max": 47.65}, "blit": {"p50": 8.93, "p99": 9.27, "max": 25.87}, "canvas": {"p50": 0.46, "p99": 0.82, "max": 7.43}, "frame": {"p50": 28.75, "p99": 29.51, "max": 69.3}, "rows blitted": {"p50": 12, "p99": 23, "max": 416}, "red": true, "where": "in the UI's process", "commit": ""}`
- sideways bar, in-process first: `{"drag": "bar", "plugin": "omx-geq", "control": "band08", "size": "1024x416", "frames": 1143, "fps": 38.1, "input": {"p50": 0.34, "p99": 0.57, "max": 2.73}, "draw": {"p50": 25.04, "p99": 26.08, "max": 97.53}, "blit": {"p50": 0.53, "p99": 0.78, "max": 21.63}, "canvas": {"p50": 0.18, "p99": 0.33, "max": 5.97}, "frame": {"p50": 26.08, "p99": 27.12, "max": 102.11}, "rows blitted": {"p50": 0, "p99": 0, "max": 416}, "red": true, "where": "renderer process", "commit": ""}`
- sideways bar, in-process first: `{"drag": "band dot", "plugin": "omx-eq8", "control": "b3_freq", "size": "1024x416", "frames": 1001, "fps": 33.4, "input": {"p50": 0.39, "p99": 0.61, "max": 1.38}, "draw": {"p50": 20.1, "p99": 20.58, "max": 26.08}, "blit": {"p50": 8.94, "p99": 9.18, "max": 35.26}, "canvas": {"p50": 0.45, "p99": 0.74, "max": 16.53}, "frame": {"p50": 29.92, "p99": 31.19, "max": 65.87}, "rows blitted": {"p50": 12, "p99": 23, "max": 416}, "red": true, "where": "renderer process", "commit": ""}`
