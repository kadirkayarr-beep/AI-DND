# Asset notes (plan parts D0, D1, D)

Every file below was compressed before it entered the repository. Sources stay outside the repository.

| File | Source | Made with | Size |
| --- | --- | --- | --- |
| `logo/ouroboros-day.mp4` | Owner-generated loop `3_efektli_loop.mp4` (owner's own generation, no third-party licence); the selected 8 s loop `ouroboros_loop.mp4` | ffmpeg: 0.5 s crossfade so the loop seam is invisible, 720 px, paper colour levelled to pure white (video is multiplied into the page, so white vanishes), H.264 crf 27, no audio | ~1.3 MB |
| `logo/ouroboros-night.mp4` | Same loop | As above, then negated and tinted warm paper colour on pure black (screened into the page) | ~1.2 MB |
| `logo/ouroboros-day-still.jpg`, `logo/ouroboros-night-still.jpg` | First frame of each video | ffmpeg | ~60 KB each |
| `favicon.png` | First frame `ouroboros_ilk_kare.png`, ring cropped | ffmpeg, 96 px | ~20 KB |
| `audio/nordisk-ritual.mp3` | "Nordisk Ritual" (`odinslefteye.mp3`), owner-generated music, no third-party licence | ffmpeg libmp3lame 80 kbps stereo 44.1 kHz, metadata stripped | ~2.2 MB (source 5.4 MB) |

Replacing a file: keep the same name; videos must keep a flat white (day) or flat black (night) ground, because the page blends them with multiply and screen instead of an alpha channel.
