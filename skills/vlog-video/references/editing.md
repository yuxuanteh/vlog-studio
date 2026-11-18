# Editing: the index, edit lists, checks, the pages, subtitles, music, privacy

## Knowing the footage (step 3, once per trip)
| Tool | What it writes into `<trip>/work/` |
|---|---|
| `footage_index.py <trip>` | `footage-index.md / .json`: every clip with its start time, length, place (its folder, or `labels.csv`) and what is said in it; `transcript/<clip>.txt`; `contact/` (frames of each clip); `mosaic/<place>.jpg` (one middle frame per clip, a folder read in one look) |
| `footage_proxy.py <trip>` | 720p working copies in `<studio>/trips/<trip>/proxy/` (same frame rate and sound, so times match) |
| `clip_score.py`, `clip_motion.py` | `clip-scores.json` (shake, sharpness, exposure, the steadiest three seconds) and `motion/<clip>.json` (shake, pan and movement for every second) |
| `photo_mosaic.py` | `mosaic-photos/`, `photo-index.csv` |
| `word_index.py <trip> <clip>` | `words/<clip>.json`: the time of every word of a recording whose voice will be used |
| `vlog_qalign.py <trip> <clip>` (the `align` part, run with `<studio>/.venv-align`) | `words/<clip>.aligned.json`: the same words with exact starts and ends |
| `vlog_limits.py <trip>` | how this trip's shake compares with the default limits; a trip's own limits go into `work/trip-settings.json` only after the director agrees |

Pick shots from the mosaics, the motion files and the transcripts, never from a clip's name or a guessed time.
`work/trip-settings.json` holds the trip's own words: `fixes` (what the speech model mishears: place and personal
names), `words` (names a Chinese word splitter must keep whole), `meta` (things said to the editor, cut by
default). Fill `fixes` from the itinerary before indexing.

## The edit list: `<trip>/work/edl/<id>.py`
A small file of blocks, built to the approved story plan. `vlog_new.py video` writes an empty one.
```python
W, H = 1920, 1080            # 16:9; a vertical video: 1080, 1920
VIDEO = "v01-old-town"       # the folder under videos/
BLOCKS = [
    V("C0006", 9.3, 14.3, ["C0386@2+3", "C0390@3"], cap="Old town"),   # voice of recording C0006 from 9.3 to 14.3 s
    S(["C0367@4+3"], gain=0.9),                                         # a clip with its own sound, nobody talking
    M(["C0101@2+2", "C0102@0+2"]),                                      # montage on music only
    T("Two days in the old town", ["C0200@5+4"]),                       # title moment
    N("A line not recorded yet.", ["C0210@1"]),                         # shown as text until it is recorded
    E(["C0300@0+6", "C0301@2+6"], next="the market at night"),          # end card, 12 s (16:9 only)
]
TRACKS = [(0, "Track Title"), (3, "Another Track")]   # music from block 0 and from block 3 on
FIX = [("heard", "meant")]   # mishearings of this video only
```
- **V** cuts snap to word edges; long pauses shrink; subtitles are timed word by word. `sync=True` keeps every
  pause (the picture is the speaker). `"SELF>27.0"` among the pictures = the voice's own clip at that moment.
- **Pictures:** `"C0394@12+5"` = clip C0394 from second 12 for 5 s (without `+5` it runs until the voice needs the
  next one). `=+5` pins the start (it never slides to a calmer stretch). `"P:DSC08630+5"` = a photo. Suffixes, in
  this order: `%0.3` where a crop to the other shape sits (0 = left / top, 1 = right / bottom) · `*0.5` slow motion ·
  `>412.3` start this picture when the voice reaches that second of its recording · `^` force / `~` skip steadying ·
  `!name` a drawn effect.
- **Options:** `cap=` place tag (shown small when the place changes) · `src=` a source line, `src_at=` the second
  of the voice where it appears · `name=True` the name tag · `fade="in" | "out" | "inout"` · `gain=` the clip's own
  sound.
- **Music levels** follow the kind of block; `MIX_REL = {"V": -18, ...}` in the edit list changes them (dB under the
  voice).
- A video keeps to one shape. A long video and its short are two edit lists that may use the same recordings.

## Building: `vlog_run.py <trip> <id> [<id> ...] [--final]`
The only way to render. In order, stopping at the first thing that is wrong:
1. **Self-test** (when a script or an edit list changed).
2. **Check** of each edit list: pictures long enough for their voice, text that would run off the frame, the
   director's sheet still followed (`STOP`, `TEXT TOO WIDE`, `SUB ORDER`, `SUB GAP`, `WARNING` lines).
3. **Side effects:** every shot and subtitle that changed since the copy the director watched (`CHANGE`), and
   anything broken (`WARN`: a changed shot that shakes or runs out, footage used twice, the same words heard twice,
   a put-back word gone). Tell the director the changes in short and every WARN; record their answer with
   `vlog_precheck.py <trip> <id> --accept "<words of the warning>"` so it is never asked again. Before a first cut
   every shot is checked and the warnings are yours to fix.
4. **Faces** (the `privacy` part): each shot used with a recognisable face and no decision stops the run (`ASK`).
5. **Stills:** every on-screen text redrawn and compared with the stills the director approved; a change stops the
   run until they have seen it (`--accept-stills`, then `vlog_stills.py … --approve`).
6. A **final** first runs as a **rehearsal** at a tiny size (a crash shows in minutes, not after an hour).
7. The **build**, under a watchdog that stops a frozen run; then the picture check (`vlog_piccheck.py`), and for a
   final `vlog_sharp.py` (the softest shots at full size) and `vlog_srt.py`.
`READY <file>` names the result: `videos/<video>/preview/<id>-phone.mp4` (checking copy) or `publish/` (final).

## The pages: `vlog_editor.py <trip>` → http://localhost:8765 (keep it running in the background)
- **Review page** (`/review`): the director plays the checking copy, pauses, taps a ready note (too short, shaky,
  use another shot, picture does not match the words, subtitle wrong, blur this, check this fact…) and may add a
  word. Each note is saved with the time, the shot (clip and second) and the subtitle: `work/review/<id>.notes.json`.
  Read that file; do not ask for written feedback.
- **Editing page** (`/`): the video's voice as words. Click a word and press X to cut it or bring it back; drag a
  word to the next subtitle; type in a subtitle to correct it; drag on the waveform to cut or put back sound the
  speech model never wrote down (an "um", a clipped word end); Delete removes a whole line. Marks inside a
  subtitle: `[ ]` or 〔 〕 = cut this voice · `/` = split into two subtitles · `+` at the end or start = join to the
  next / previous · `( )` = a note to you, never shown.
- Saving writes the subtitle sheet `work/subtitles/<id>.xlsx` (it can be edited in Excel too) and
  `<id>.voice.json`. **These are final**: the next build follows them exactly, and an edit list that no longer
  reaches an edited row stops the run instead of losing it. Read the director's `( )` notes: the side-effect check
  lists them.
- The page language is `[ui] language` (English or Chinese).

## Subtitles
Burned in, following the sheet exactly: the director's rows, splits and joins, in their order. One line of about
20 units on a horizontal video (a Chinese character = 1, about two letters = 1), up to two lines of 24 on a vertical
one, placed above the platform's buttons. After the final: `vlog_srt.py <trip> <id>` writes the spoken-language
subtitle file and `work/subtitles/<id>.translate.tsv`; fill the translation columns (`[language] subtitle_second`,
`_third`), run it again, and the translated files appear in `publish/`. The files are named
`subtitles.<language>_<COUNTRY>.srt` (a short: `short/short.<language>_<COUNTRY>.srt`), e.g. `subtitles.en_GB.srt`:
Facebook accepts subtitle files only in this shape, and YouTube takes the same files. The country follows the
language; `[language] subtitle_locales = {en = "en_AU"}` sets it by hand. A subtitle that changed since it was
translated stops it.

## Music (`TRACKS`, the `music_fit` part)
Tracks are files in the music folder (`Title - Artist.mp3`). A track plays from its block to the next track's
block; pieces are cut only on bar lines, the track's own ending lands at the end of its part, a montage can be cut
to the beat. `vlog_tracks.py` alone lists the library. Propose tracks in the story plan (mood per part, a few
candidates each); the director listens and picks. **A track's licence must cover every platform the video goes
to**; keep a used-list (`music-used.md`) and the credit line each library asks for. When the director adds music in
a platform's own app instead, build without `TRACKS`.

## Privacy (the `privacy` part)
`vlog_faces.py` lists every shot used in which a face is clearly recognisable; nothing is blurred by default.
Decisions live in `work/privacy.json`, by stretch of clip, so a shot that moves a little keeps its answer:
```json
{"C0236": [[3.0, 9.5, "ok", "the presenter"], [12.0, 14.0, "blur", "family at the next table"]]}
```
`ok` = leave, `blur`, `cut` = do not use this stretch. Car plates and screens are not found by a model: look at the
sheet it writes. A thing to blur or mark through a shot (a QR code, a ticket) is a tracked effect: `!qr` on the
picture; other effects written for one shot live with the trip in `work/fx.py`. Without the part, the run says
`faces: SKIPPED` every time and you look yourself.

## Steadying and brightness
A shot whose shake is over the limit is steadied by itself (a slight crop); `^` forces it, `~` skips it;
`[look] steady = false` turns it off. Brightness is levelled between shots of one place, without changing colours;
`[look] level_brightness = false` leaves pictures exactly as filmed. Exposure, focus and white balance are fixed
on site: a soft or blown-out shot is replaced, not rescued.

## Thumbnails and covers
**Ideas first, as text**, for thumbnails and for short covers alike (one line each: what is seen, the two or three
words, why someone would tap), with the frame or photo each would use. Make only what the director picks or
corrects. The idea belongs to that video (a pair of pictures, an object, a moment from the footage), never a fixed
layout with the title swapped.
- **The presenter may be on a thumbnail or a short cover.** When they are, never a plain photo with words on it
  (flat, no depth): cut them out, enlarge them and put them over the same picture or another one as the
  background, so there are layers. The words never overlap them. If the frame cuts them at an edge, the cut-out
  runs off the same edge (no floating head).
- A cover without the presenter is fine too when the place carries it.
- **A short's cover** is 1080×1920 with the words and the subject inside the centred 1080×1350 (profile grids
  crop the rest), text at least 80 px high. **The same file is the YouTube Shorts thumbnail and the Reels cover.**
- Two to four words; one real place from the trip; no blur on a background that is itself the subject. A drawn
  mark (an arrow, a circle) only where it points at something true.
- Pick the exact frame by pulling it and looking (a contact-sheet tile can be a second off: eyes closed, arm
  down), and look at every picture at quarter size before sending. `vlog_thumbs.py <trip> grab <clip>:<second>` pulls full-size
stills, `cut` cuts the person out (the `cutout` part), `check` checks sizes and file limits. The design is a small
file with the trip (`work/thumbs/layout.py`). Sizes and each platform's crop: platforms.md.
