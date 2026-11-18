---
name: vlog-setup
description: Set up, update, move or uninstall the Vlog Studio pipeline for travel vlogs and site-visit videos made from real footage. Checks the computer first and says about how long each step will take on it, asks whether the person makes horizontal videos, vertical Reels / Shorts or both, which platforms they post to (YouTube, Instagram, Facebook, TikTok and others have different rules), whether finished videos should be 4K or 1080p, and whether they film on a camera or only a phone; explains what every tool is for and asks whether the person needs it BEFORE installing it (so unneeded parts are skipped and disk space is saved); then tries the pipeline on a handful of the person's own clips. Use when the user installs the vlog-studio plugin, says "set up my vlog studio", wants to make a first vlog without a studio, wants to add or remove a part (speech model, privacy, music, thumbnails, aligner), changes what they make or where they post, asks how long things will take on their computer, updates the plugin, moves to another machine, or wants to uninstall.
---

# Vlog studio setup

The person may not code. You do every command; they answer questions and look at pictures. Speak their language,
short sentences, everyday comparisons for technical things.

**Rules for the whole setup**
1. **Nothing is downloaded or installed before the person has said yes to that part**, knowing what it is for, who
   can skip it and how big it is. One question per part (AskUserQuestion when available). A "no" is respected and
   recorded; the part can be added later with one sentence.
2. **Measure before promising.** Run the hardware probe first and say what their computer will take per step.
3. **Never overwrite what exists**: an existing studio, `vlog.toml`, trips, edit lists, subtitle sheets.
4. **Their footage is theirs.** Files in a trip's `raw/` are never moved, renamed or deleted.

The plugin's files sit next to this skill: `<plugin>/studio/` (tools, `vlog.example.toml`, `platforms.toml`,
`requirements/`), where `<plugin>` = `<this skill's base directory>/../..`.

## 0 · What is already here?
Look first: an existing studio folder (`vlog.toml` beside `scripts/`), a trips folder with `work/` folders in it,
which parts are installed (`setup_studio.py status`). Say in two lines what you found: a new set-up, or an update
(section 9).

## 1 · The computer: what it is and how long things will take
Run the probe from the plugin copy; it needs only Python (use `uv run --python 3.12 --no-project python`, or any
`python` 3.11+; if neither exists, ask to install uv first, about 30 MB):

```
python <plugin>/studio/scripts/probe.py --minutes <their usual video length, default 8> --footage <hours filmed per trip, default 2>
```

Tell the person in a small table: what the computer is; its speed against the reference laptop; **about how long
each step takes**: writing down the footage, the 720p working copies, a checking copy of one video, the final at
**1080p and at 4K side by side**, a 9:16 short; and everything under "WORTH KNOWING" (little memory, an NVIDIA card,
a hardware encoder, low disk space, how much disk a trip's working copies and render cache take).
Be honest: rough numbers (half to double), the computer's own time only.

## 2 · Interview (ask, then wait). These decide what gets installed and how every video is made.
1. **What do you make?** Horizontal videos (16:9, the long vlog), vertical videos (9:16: Reels, Shorts, TikTok), or
   **both** (a long vlog and shorts cut from the same trip). → `[formats] wide`, `tall`, `default`.
   If both: say that one trip's footage serves both, and that filming with the subject in the middle third lets a
   9:16 short be cropped from a horizontal clip.
2. **Where do you post?** Show `python scripts/vlog_platform.py list` in plain words (YouTube, YouTube Shorts,
   Instagram, Facebook, TikTok, 小红书, 哔哩哔哩; they may name another). → `[platforms] post_to`. For each platform
   they name, tell them in one line what is different there (longest length, links in the text or not, cover
   crop, where buttons cover the picture) from `platforms.toml`, and say that these rules change: **look at the
   platform's own help page for any limit that matters and correct `platforms.toml`** (its `checked` month says how
   old each row is). A platform that is not in the file: ask what they know of its rules and add a block.
3. **4K or 1080p** for finished horizontal videos? Give the two time estimates from the probe and the disk space
   side by side (4K takes about four times as long to render and four times the space; it only pays when the
   footage is 4K and viewers watch on large screens). → `[formats] final_wide`. Vertical videos are 1080×1920.
4. **What do you film with?** A camera with a microphone, a phone only, or both. Phone-only is fully supported
   (filming.md "Phone only"): note it in `CHANNEL.md` so shot lists and checks follow it.
5. **Do you talk in your videos?** To the camera on site, an evening recap, a voice-over recorded later, or no
   talking (music and pictures). This decides the `whisper` part.
6. **Do you already have footage** you want to turn into a video (a past trip), or is the trip still ahead? Both
   work; the first uses the footage-only path (the vlog-video skill, "Footage you already have").
7. Channel name, the name and one honest line for the name tag, narration language, translated subtitle languages,
   credits line for the end card, logo files if any.
8. Where the **trips folder** lives (their footage and finished videos; may be an external drive or a synced
   folder; originals can be large) and where the **studio folder** lives (tools, models, 720p copies, render cache:
   a local disk with room: the probe says how much).

## 3 · The parts: explain, ask, then install
`python <plugin>/studio/scripts/setup_studio.py list` prints every part. For each one say **what it does for them,
who can skip it, how big it is**, then ask. Recommend from the interview.

| Part | What it gives | Skip it when | Size |
|---|---|---|---|
| `core` | the studio's own Python, ffmpeg and ExifTool: index, cuts, steadying shaky shots, evening out brightness, subtitles, encoding | never | about 450 MB |
| `fonts` | free fonts for subtitles, place tags, titles | never | 3 MB (Latin) – 45 MB (Chinese) |
| `whisper` | writes down what is said in every clip: footage is found by words, cuts land between words, subtitles are timed | no talking in their videos | 3.1 GB (large-v3) · 1.7 GB (medium) · 0.7 GB (small) |
| `privacy` | finds faces of passers-by in the shots used and stops the render until each is decided (leave / blur / cut); follows a thing through a shot to blur or mark it | they never film other people, or will check every shot themselves | about 1 MB |
| `music_fit` | fits a music track to the cut on bar lines, ending on its own ending | no music | about 300 MB |
| `cutout` | cuts a person out of a frame for thumbnails and covers | thumbnails from whole frames are enough | about 1.2 GB |
| `align` | exact start and end of every word, so cuts inside sentences are clean | they are fine fixing an occasional clipped word on the editing page | about 3 GB |

Steadying and the light colour levelling are part of `core` (no download). Ask about them as **behaviour**: steady
shaky shots automatically (yes is usual); level brightness between shots, or leave colours exactly as filmed. Record
the answers in `CHANNEL.md`.

Order once choices are made (each command only after its yes):
1. Copy the plugin's `studio/` folder to the studio location (never over an existing studio), `cp vlog.example.toml
   vlog.toml`, then `setup_studio.py set paths trips "<trips folder>"` and the `[language]` values (the installer
   reads the narration language).
2. `python scripts/setup_studio.py install core`. From here on use the studio's Python (`.venv/Scripts/python.exe` on
   Windows, `.venv/bin/python` elsewhere). If it prints `MISSING ffmpeg` or `MISSING exiftool`, show the one-line
   install command, ask, run it, and set `[paths] ffmpeg_bin` / `exiftool` when the program is not on PATH.
3. `install fonts`; then only the chosen ones of `install whisper --model <choice>`, `install privacy`,
   `install music_fit`, `install cutout`, `install align`. For each part declined:
   `setup_studio.py set components <part> false`.
4. `python scripts/setup_studio.py status`: read it to the person in two lines.

## 4 · Write the settings
`setup_studio.py set <section> <key> <value>` (values are TOML: text in double quotes, lists in brackets, true /
false bare). From the interview: `[formats]` (wide, tall, default, final_wide), `[platforms] post_to`, `[channel]`
(name, presenter, presenter_title, credits, end_head, end_next in their language, logo files), `[language]`
(narration, length_unit = "cjk" for Chinese / Japanese else "words", pace, subtitle_second / _third), `[ui]
language` ("en" or "zh": pages and sheets), `[whisper] device`.
Then, in the folder that holds the trips folder, from the templates in `<plugin>/channel-template/`: `CHANNEL.md` (who the viewers are, what is made and in which
shapes, the platforms and what differs on each, 4K or 1080p, camera or phone, the behaviour answers, music source
and its licence, the time estimates) and `voice-examples.md` (from the same template folder: how this person talks; filled from their own
recordings and their edits).

## 5 · Music: ask how they want it
- **Library tracks** they download themselves (for example the YouTube Audio Library; a track's licence must cover
  every platform they post to: music cleared for YouTube is not automatically cleared for Instagram or TikTok),
  into the music folder as `Title - Artist.mp3`. Needs `music_fit`.
- **Their own music.** Needs `music_fit`.
- **The platform's own music added at upload** (common for Reels and TikTok): the video is built without music,
  and they add a track in the app. Say that such a video then differs per platform.
- **No music.**
Record the answer in `CHANNEL.md`.

## 6 · Try it on their own footage (offer it; it is the real test)
Ask for **a handful of their own clips**: five to ten, a minute or two in all, one of them with them talking
(a recap or a line to the camera). No made-up sample: their own camera, voice and language are what need testing.
1. `python scripts/vlog_new.py trip try-out`; they copy the clips into `<trips>/try-out/raw/` (you may copy for
   them when they give a path; never move).
2. `footage_index.py try-out`, `footage_proxy.py try-out`, `clip_score.py try-out`, `clip_motion.py try-out`,
   `photo_mosaic.py try-out` if there are photos. Show them `work/footage-index.md` and a mosaic: this is how you
   will know their footage.
3. `word_index.py try-out <the clip with talking>`.
4. `vlog_new.py video try-out v01-try` (the shape(s) they chose), fill the edit list with one voice block over three
   or four clips and one block of a clip's own sound, then `vlog_run.py try-out v01-try` (and `v01-try-short`).
5. Start the pages (`python scripts/vlog_editor.py try-out`, http://localhost:8765) and let them try the **review
   page** (watch, tap a note) and the **editing page** (cut a word, fix a subtitle).
6. If they chose `privacy` and the run stops on a face: that is the part working. Ask, record the answer in
   `work/privacy.json`, run again.
Use the measured time of this run to correct the estimate from section 1. Say what worked and what you would change
in how they film (sound level, shake, framing for 9:16). Keep or delete the try-out trip as they wish.

## 7 · Finish
One short message: what is installed and what was skipped (with the sentence that adds a part later), what they
make and where it goes, 4K or 1080p, the time estimate for a usual video, and how to start: "plan my trip to …" or
"here is footage from …, make a vlog".

## 8 · Changing the answers later
"I also want Reels now", "I started posting to TikTok", "make finals 4K": change `[formats]` / `[platforms]` with
`setup_studio.py set`, update `CHANNEL.md`, and say what changes for videos in progress (a new shape needs its own
edit list; a new platform gets its own text in the upload package).

## 9 · Updating, freeing space, moving, uninstalling
- **Update**: `claude plugin marketplace update vlog-studio`, then `claude plugin update vlog-studio@vlog-studio`.
  Copy the changed files of `<plugin>/studio/scripts/` and `requirements/` into the studio after a backup of the old
  `scripts/` folder. **Never overwrite** `vlog.toml`, `platforms.toml` if they corrected it (merge new platforms
  only), anything under a trip. Add missing keys from `vlog.example.toml`. Run `python scripts/vlog_selftest.py`
  afterwards and read `CHANGELOG.md` to them.
  If a build then stops with "VERSION is still …; bump VERSION", the update changed a tool whose results are cached:
  delete `<studio>/codever.json` and the render cache (`<studio>/render/<trip>/<id>`) of videos not yet finished.
- **Free disk space**: `setup_studio.py status`. The render cache (`<studio>/render`) and the 720p copies
  (`<studio>/trips`) of finished trips are the big ones and are made again when needed; `remove whisper | cutout |
  align | music_fit | privacy` for parts no longer wanted. Ask before each and say what stops working. Never touch
  `raw/`.
- **Move to a new computer**: run this setup there with the same choices, copy `vlog.toml` and `platforms.toml`
  across; trips come with their folder. Run the probe again.
- **Uninstall**: delete the studio folder; `claude plugin uninstall vlog-studio@vlog-studio`. Their trips folder is
  theirs: never delete it.
