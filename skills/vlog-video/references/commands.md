# Command sheet

All commands: from `<studio>/scripts`, with the studio's own Python (`../.venv/Scripts/python.exe` on Windows,
`../.venv/bin/python` elsewhere). Set `PYTHONIOENCODING=utf-8` when a console cannot print the narration language.
Long ones (index, working copies, renders) run in the background.

| Step | Command | Result |
|---|---|---|
| New trip | `vlog_new.py trip 2026-05-kyoto` | `<trips>/<trip>/raw, work, videos`, `decisions.md`, `work/trip-settings.json` |
| New video | `vlog_new.py video <trip> v01-old-town [--format wide\|tall\|both]` | `work/edl/v01-old-town.py` and / or `v01-old-town-short.py` |
| Index | `footage_index.py <trip>` | `work/footage-index.md`, transcripts, contact sheets, mosaics (new files only on a rerun) |
| Working copies | `footage_proxy.py <trip>` | 720p copies in `<studio>/trips/<trip>/proxy/` |
| Shake and sharpness | `clip_score.py <trip>` · `clip_motion.py <trip> [clips]` | `work/clip-scores.json`, `work/motion/` |
| Photos | `photo_mosaic.py <trip>` | `work/mosaic-photos/`, `photo-index.csv` |
| This trip's limits | `vlog_limits.py <trip>` | how its shake compares with the defaults |
| Word times | `word_index.py <trip> <clip> [...]` | `work/words/<clip>.json`, `.txt` |
| Exact word times | `<studio>/.venv-align/…/python vlog_qalign.py <trip> <clip> [...]` | `work/words/<clip>.aligned.json` |
| A clip or time the director names | `vlog_pick.py <trip> <clip>@<second>+<length> [...]` | shake, too short, already used |
| Check an edit list | `vlog_build.py <trip> <id> --check [--phone]` | `work/edl/<id>.report.txt`, `.cues.txt`; problems printed |
| **Render** | `vlog_run.py <trip> <id> [<id> ...] [--final]` | every check in order, then the checking copy (`preview/<id>-phone.mp4`) or the final (`publish/`) |
| After the director's answers | `vlog_precheck.py <trip> <id> --accept "<words>"` · `vlog_run.py … --accept-stills` · `vlog_stills.py <trip> <id> --approve` | an answered warning is never asked twice |
| Review + editing pages | `vlog_editor.py [trip] [port]` | http://localhost:8765 (editing) and `/review` |
| Check kept voice against the sheet | `vlog_editcheck.py <trip> [id]` | words kept but not heard, cut but still heard |
| Faces | `vlog_faces.py <trip> <id>` | `ASK` lines, a sheet of the shots; decisions in `work/privacy.json` |
| Picture check | `vlog_piccheck.py <trip> <id>` | `work/review/<id>.piccheck.txt` |
| Rehearse a render | `vlog_rehearse.py <trip> <id> [--phone-only\|--final-only]` | the real build at a tiny size in `<studio>/rehearse/` |
| Sharpness of a final | `vlog_sharp.py <trip> <id>` | the softest shots at full size |
| Subtitle files | `vlog_srt.py <trip> <id>` | spoken-language file + `work/subtitles/<id>.translate.tsv`; translated files once it is filled |
| Music library | `vlog_tracks.py ["Title" …]` | length, tempo, bars |
| Thumbnails | `vlog_thumbs.py <trip> grab <clip>:<second> …` · `cut <still> …` · `check` | `work/thumbs/src`, `cut`, sizes checked |
| Platforms | `vlog_platform.py list` · `check <video.mp4> [platform …] [--cover …] [--text …]` | OK / WARN per platform |
| Self-test | `vlog_selftest.py` | every known edge case; run after changing any script |
| Parts | `setup_studio.py list` / `status` / `install <part>` / `remove <part>` / `set <section> <key> <value>` | see the vlog-setup skill |
| This computer | `probe.py [--minutes 8] [--footage 2] [--model …] [--json]` | hardware, speed, time per step at 1080p and 4K |

## Quick look at a video (contact sheet)
```bash
ffmpeg -v error -y -i video.mp4 -vf "fps=1/4,scale=320:180,tile=4x6" -frames:v 1 -update 1 sheet.png
```
