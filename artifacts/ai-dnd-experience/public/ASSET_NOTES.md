# Asset notes (plan parts D0, D1, D)

Every file below was compressed before it entered the repository. Sources stay outside the repository.

| File | Source | Made with | Size |
| --- | --- | --- | --- |
| `logo/ouroboros-skin.png`, `logo/ouroboros-head.png`, `logo/ouroboros-profile.png`, `logo/ouroboros-phase.png` | v0 graphite ouroboros (owner-approved 2026-11-17, Vercel v0 output `index-v8.zip`; data extracted from the zip, no code run). Textures read by the WebGL shader | Decoded from the base64 in the zip's `ouroboros-textures.ts` to plain PNG files, unchanged (not re-compressed: ffmpeg/other tools would change the shader's data channels) | ~310 KB, ~335 KB, <1 KB, <1 KB |
| `logo/ouroboros-emblem.png`, `logo/ouroboros-mark.png` | Same zip: static emblem (no-WebGL fallback) and the small 24-40 px silhouette | Same, used as a CSS mask coloured by the theme | ~313 KB, ~10 KB |
| `favicon.png` | First frame `ouroboros_ilk_kare.png`, ring cropped | ffmpeg, 96 px | ~20 KB |
| `audio/nordisk-ritual.mp3` | "Nordisk Ritual" (`odinslefteye.mp3`), owner-generated music, no third-party licence | ffmpeg libmp3lame 80 kbps stereo 44.1 kHz, metadata stripped | ~2.2 MB (source 5.4 MB) |

Replacing a file: keep the same name. The old looped videos and stills were removed when the v0 logo came in; they stay in git history. Night uses the same logo with `filter: invert(1)`, so the textures are one dark-ink set for both themes. The emblem and mark PNGs are masks (alpha is the drawing).
