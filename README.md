# Vlog Studio

**English** · [中文](README.zh-CN.md)

A Claude Code plugin for making travel vlogs and site-visit videos from your own footage, where Claude does the
editing crew's work and you direct. You film, talk about your day, watch the cuts and say what to change. You write
no code.

It makes **horizontal videos (16:9), vertical ones (9:16: Reels, Shorts, TikTok), or both from the same trip**, and
writes the upload text for each platform you post to, because they do not share rules.

It was built with and for the channel 金釘子 GoldenSpike, on real trips, and then opened up for any language and
any trip. It is a separate plugin from [Explainer Studio](https://github.com/yuxuanteh/explainer-studio) (studio
explainers with animation); the two share nothing and can be installed side by side.

## Install and start: one prompt

Open a folder for your channel in Claude Code (terminal, desktop app or IDE extension), paste this, and fill in the
last lines:

```text
Install the Vlog Studio plugin and set up my vlog studio.
1. In the terminal run:  claude plugin marketplace add yuxuanteh/vlog-studio
   then:                 claude plugin install vlog-studio@vlog-studio
2. Find the installed plugin folder (under ~/.claude/plugins), read skills/vlog-setup/SKILL.md in it and follow it
   step by step. Start by checking my computer and telling me about how long each step will take on it. Ask me
   whether I make horizontal videos, vertical ones or both, and where I post. Before you install or download
   anything, tell me what it is for and how big it is, and ask me whether I need it.
3. When the studio is ready, try it on a few of my own clips with me.
My channel: <name>. I make <horizontal vlogs / Reels and Shorts / both> and post to <YouTube, Instagram, TikTok, …>.
I film with <a camera / my phone / both>. I speak <language> in my videos.
I have <a trip coming up / footage from a past trip I want to turn into a video>.
```

Prefer to type the commands yourself? `/plugin marketplace add yuxuanteh/vlog-studio`, then
`/plugin install vlog-studio@vlog-studio`, then say "set up my vlog studio".

After that it is plain sentences: "plan my trip to Kyoto", "the footage is in raw", "here is footage from last
year, make a vlog", "that shot is shaky, use another", "make the final".

## What you are asked at setup

1. **Your computer is checked first.** You get a table of about how long each step takes on it, with a 1080p final
   and a 4K final side by side, before you decide anything.
2. **Horizontal, vertical, or both?** This decides how every video is planned, cut and sized.
3. **Where do you post?** YouTube, YouTube Shorts, Instagram, Facebook, TikTok, 小红书, 哔哩哔哩, or another. Lengths,
   links, cover crops and where buttons cover the picture differ per platform; each one gets its own text.
4. **4K or 1080p** for finished horizontal videos, with the time and disk space each costs on your computer.
5. **Camera or phone?** Filming only on a phone is fully supported.
6. **Each tool, before it is installed:** what it is for, who can skip it, how big it is.
7. **A try-out on a handful of your own clips**: index, cut, the review page and the editing page, in your own
   language, with your own camera's files.

### The parts, and who can skip them

| Part | What it does for you | You can skip it when | Download |
|---|---|---|---|
| Core | The studio's own Python, ffmpeg and ExifTool: the footage index, cuts, subtitles, encoding. It also steadies shaky shots and evens out brightness between shots (both can be turned off) | never | about 450 MB |
| Fonts | Free fonts for subtitles, place tags and titles | never | 3 MB (Latin) to 45 MB (Chinese) |
| Speech recognition (Whisper) | Writes down what is said in every clip, on your own computer. Footage is found by words, cuts land between words, subtitles are timed | nobody talks in your videos | 3.1 GB (best), 1.7 GB (medium) or 0.7 GB (small) |
| Privacy | Finds faces of passers-by in the shots you use and stops the render until you have decided each one (leave, blur, cut). Follows a ticket or a QR code through a shot to blur it | you never film other people, or will check every shot yourself | about 1 MB |
| Music fitting | Shortens or lengthens a music track on its bar lines so it ends on its own ending | no music, or music added in the platform's app | about 300 MB |
| Thumbnail cut-out | Cuts you cleanly out of a frame for thumbnails and covers | thumbnails from whole frames are enough | about 1.2 GB |
| Precise word timing | Finds the exact start and end of every word, so cuts inside sentences are clean | you do not mind fixing a clipped word now and then on the editing page | about 3 GB |

A full install is about 8 GB; the smallest useful one (core, fonts, the small speech model) is about 1.2 GB.

### How long things take

On the reference laptop (Intel Core Ultra 7 155H, 16 cores, 16 GB memory, no separate graphics card), with 4K camera
footage. The setup measures your own computer and scales these.

| Step | Computer time |
|---|---|
| Once per trip, for 2 hours of footage: writing down what is said (half an hour of talking) | about 20 minutes |
| Once per trip: looking through the footage (contact sheets, shake, sharpness) | about 30 minutes |
| Once per trip: 720p working copies | about 40 minutes |
| A checking copy of an 8-minute video (each review round) | about 20 minutes |
| The final of that video at 1080p | about 40 minutes |
| The final of that video at 4K | about 1 hour 45 minutes |
| A 1-minute vertical video: checking copy, then final | about 5 and 10 minutes |

Rough numbers: expect half to double. Disk: an hour of 4K footage is about 45 GB (yours, wherever you keep it); the
studio adds about 1 GB of working copies per hour of footage and about 3 GB of render cache per minute of 4K video
(a quarter of that at 1080p), both deleted when a trip is done.

## How a video is made

Nine steps. Claude stops where it says **Stop** and waits for your OK.

1. **Trip plan** (skipped when the footage already exists). What each place is, from real sources; a shot list per
   place; what you might say there. **Stop.**
2. **You film.** A recap every evening: where you went, what surprised you, what went wrong. The recaps are the
   narration.
3. **Index and video plan.** Every clip is written down, measured for shake and sharpness, and laid out in one
   picture per place. You get: what the footage holds, what is missing, and which videos it can become, in which
   shapes, for which platforms. **Stop.**
4. **Story plan.** One page per video, before any cutting: the one question it answers, the three or four moments
   that carry it, what is dropped, where the pauses are, the music. **Stop.** Order is decided here, where a change
   is free.
5. **Lines to re-record**, only where the footage lacks something. **Stop.**
6. **You re-record**, once, for the whole trip.
7. **First cut.** You watch it on the **review page** and tap notes, or fix words and subtitles yourself on the
   **editing page**. **Stop.** Story and pacing are locked.
8. **Music, place tags, privacy.** **Stop.**
9. **Final and upload package**: the finished files, translated subtitles, covers, and one section per platform with
   its own text. **Stop.** You upload and schedule by hand.

### Starting from footage you already have

"I have footage from last year, make a video" works. The flow starts at step 3 and first tells you honestly what
that footage can become. Clips you can no longer place are placed from your phone photos of the same days (they
carry time and place), from gaps in time, and from signs in the picture. If there is no narration, you are shown
the pictures day by day and talk about them for a few minutes; that recording becomes the voice.

## The tools, in plain words

| Tool | What it is |
|---|---|
| Footage index (`footage_index.py`) | Every clip with when it was filmed, how long it is, where, and what is said in it; one overview picture per place |
| Working copies (`footage_proxy.py`) | Small 720p copies for editing; the originals are only read for the final |
| Shake and sharpness (`clip_score.py`, `clip_motion.py`) | A number for every second of every clip, so shots are picked from what really happens in them |
| Word times (`word_index.py`, the aligner) | When each word of your voice starts and ends, so a cut never lands inside a word |
| Edit list | A short file per video: which part of which recording plays over which shots. Claude writes it from the story plan |
| The gate (`vlog_run.py`) | The one way to render. Self-test, edit check, what your edits changed and what they broke, faces, on-screen text against what you approved, a rehearsal before a final, then the render under a watchdog that stops a frozen run |
| Review page | A page on your own computer. Play the cut, pause, tap a ready-made note ("too short", "shaky", "use another shot", "blur this"…). Each note keeps the time, the shot and the subtitle |
| Editing page | Your voice as words. Click a word to cut it or bring it back, drag a word to the next subtitle, type to correct a subtitle, drag on the waveform to cut an "um" the speech model never heard. What you save is final and is never overwritten |
| Subtitle sheet | The same edits as an Excel file, if you prefer a spreadsheet |
| Privacy check (`vlog_faces.py`) | Lists every shot with a recognisable face; you decide each once |
| Steadying, brightness | A shaky shot is steadied by itself; brightness is evened out between shots of one place; colours are left as filmed |
| Music fitting (`vlog_tracks.py`) | Cuts a track only on bar lines and lets it end on its own ending; a montage can be cut to the beat |
| Platform check (`vlog_platform.py`) | Checks a finished file, its cover and its text against the rules of each platform you post to |
| Thumbnails (`vlog_thumbs.py`) | Full-size stills from your footage, you cut out of the picture, sizes checked |
| Setup tools (`probe.py`, `setup_studio.py`) | Measure your computer and estimate times; install, check and remove parts |

## Platforms

The rules the plugin knows are in one file (`platforms.toml`), each with the month it was last checked. Platforms
change their limits often, so before a limit decides something, Claude looks at the platform's own help page and
corrects the file. You can add a platform by copying a block.

## Updating, freeing space, moving, uninstalling

Say it to Claude ("update Vlog Studio", "free up disk space", "I have a new computer", "uninstall"); the setup
skill does the rest and asks before it removes anything.

- **Update:** `claude plugin marketplace update vlog-studio`, then `claude plugin update vlog-studio@vlog-studio`.
  Your settings, platform rules, trips, edit lists and subtitle sheets are never overwritten.
- **Free space:** the render cache and the working copies of finished trips are the big ones and are made again
  when needed; any optional part can be removed and added again later.
- **Move:** your trips folder carries everything of a trip; on the new computer the setup runs again.
- **Uninstall:** delete the studio folder, remove the plugin. Your trips folder is yours and is never touched.
  Files in a trip's `raw/` folder are never moved, renamed or deleted by any tool.

## What you need

- Claude Code with a Claude plan.
- Windows, macOS or Linux. Built and tested on Windows 11; macOS and Linux use the same code but are untested, so
  expect rough edges.
- 2 to 9 GB of disk for the studio, plus room for working copies and the render cache; 8 GB of memory or more
  (16 GB for 4K).
- A camera or a phone. A separate microphone helps more than anything else.

## What is not in it

- Animation and drawn maps: this pipeline is footage first. (Explainer Studio does animation.)
- A tool that writes the upload page: Claude writes it from the rules, per platform.
- Automatic posting: you upload and schedule yourself.
- Pages and sheets are in English or Chinese. Narration can be in any language the speech model knows; it has been
  used most in Mandarin. English subtitles are split by a simpler rule than Chinese ones and have had little use.

## Licences

The code and documents in this repository are MIT licensed. Nothing else is bundled; setup downloads, with your OK:
faster-whisper (MIT) and its models, FFmpeg (LGPL/GPL builds), ExifTool (Perl licence), OpenCV (Apache 2.0) and its
face and tracking models, librosa (ISC), rembg (MIT) with the BiRefNet model, the Qwen3 forced aligner
(Apache 2.0) with PyTorch, and fonts under the SIL Open Font Licence (Noto Sans, LXGW WenKai). Music keeps the
licence of wherever you got it, and that licence must cover every platform you post to.
