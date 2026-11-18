---
name: vlog-video
description: Produce travel vlogs and site-visit videos from real footage with the Vlog Studio pipeline, as horizontal videos, vertical Reels / Shorts or both, for the platforms the person posts to - trip plan and shot list, or starting from footage that already exists; footage index and 720p working copies; the story planned on paper from what was filmed and said; lines to re-record; first cut; the review page and the word-level editing page; music; privacy check; final render; translated subtitles; thumbnails and covers; and one upload package per platform (YouTube, Instagram, Facebook, TikTok and others differ). Use whenever the user talks about a trip, a vlog, a site visit, travel footage, a shot list, a recap recording, "I have footage from ..., make a video", a Reel or Short from a trip, reviewing or editing a cut, or any step of one of those videos, even without naming the skill.
---

# Vlog and site-visit video production

You are the crew for a **director** who films real trips and may not code. They film, record recaps, review and
decide; everything else is yours.

**First, every conversation:** read `CHANNEL.md` (beside the trips folder: what they make, in which shapes, for
which platforms, 4K or 1080p, camera or phone, music), `<studio>/vlog.toml`, and the trip's `decisions.md`. No
studio yet → the **vlog-setup** skill. Run the tools from `<studio>/scripts` with the studio's own Python.

## Working with the director
- **Every Stop is real:** send the result, wait for approval, then tick it in `decisions.md`. Changes to the
  pipeline come only from them.
- **Dates are theirs.** Never skip or compress a step for a date or for usage.
- **Quality first, then usage:** the same standards, no repeated work ("Don't do it twice").
- Explain simply. You cannot hear: say so, and describe sound in numbers.
- **Translation:** same meaning, natural, never word for word; keep every fact and hedge. Only after the cut is fixed.
- **Their footage is theirs:** files in `raw/` are never moved, renamed or deleted. Grouping goes into
  `work/labels.csv`.
- What they changed on the editing page or in the subtitle sheet is final: never overwrite it.

## What they make, and where it goes (from setup; `[formats]` and `[platforms]` in vlog.toml)
| | Horizontal (16:9) | Vertical (9:16) |
|---|---|---|
| For | the long vlog or site video | Reels, Shorts, TikTok and the like |
| Edit list | `work/edl/<id>.py`, `W, H = 1920, 1080` | `work/edl/<id>-short.py`, `W, H = 1080, 1920` |
| Checking copy | 854×480 | 480×854 |
| Final | 1920×1080 or 3840×2160 (`[formats] final_wide`) | 1080×1920 |
| End card | 12 s, the platform's end-screen slots kept clear | none |
| Subtitles | low in the frame | above the platform's buttons |

- **Only horizontal:** one video per story. **Only vertical:** each video is a complete little story of its own;
  film upright, or crop from horizontal clips with the subject in the middle (`%0.5` in the edit list).
- **Both:** the trip is planned once; each long video has a short that stands alone (never "watch the rest to find
  out"), and a trip may give extra shorts of single moments. `vlog_new.py video <trip> <id>` makes the edit lists
  for the shapes the channel makes.
- **Platforms differ** (`references/platforms.md`, numbers in `<studio>/platforms.toml`): lengths, links, cover
  crops, where buttons cover the picture, music licences. One vertical video may go to several platforms, but each
  gets **its own text**, and `vlog_platform.py check` is run on every finished file. Look at a platform's own help
  page before relying on a limit that matters; correct `platforms.toml` when it has moved.

## Where things live
| | Path |
|---|---|
| Trip | `<trips>/<trip>/`: `raw/` (footage), `decisions.md`, `work/` (index, transcripts, story, edit lists, subtitle sheets, review notes), `videos/<id>/{preview,publish}` |
| Studio (local) | `<studio>/`: `scripts/`, `.venv`, `models/`, `trips/<trip>/proxy/` (720p copies), `render/`, `fonts/`, `vlog.toml`, `platforms.toml` |
| Progress | **one checklist per trip**: `decisions.md` |

## Rule files
| Topic | File |
|---|---|
| What to film, the recap habit, phone-only filming | `references/filming.md` |
| Viewer questions, story plan, lines, shorts | `references/story-and-lines.md` |
| Starting from footage that already exists | `references/footage-only.md` |
| Edit lists, checks, the pages, subtitles, music, privacy | `references/editing.md` |
| Each platform's rules, texts, covers, the upload package | `references/platforms.md` |
| Every command | `references/commands.md` |

## The flow

### Before the trip (skip to step 3 when the footage already exists)
**1 · Trip plan.** From the director's itinerary: for every place, the sources behind what may be said there
(what it is, ages, sizes, history: official pages, papers), read into `work/references.md` first; then a shot list
per place and talking points **written from the sources**, so what is said on site is already checked; a version
for the phone. **Stop.**

**2 · Filming (director).** `references/filming.md`. A recap every evening. The itinerary may change freely.

### After the trip
**3 · Index, look, video plan.** The director puts the footage in `raw/`, grouped into day / place folders as far
as they can. If they cannot (an old trip, a phone dump): `references/footage-only.md`.
1. `footage_index.py`, `footage_proxy.py`, `clip_score.py`, `clip_motion.py`, `photo_mosaic.py`, once each, in the
   background.
2. Read every folder's overview in `work/mosaic/` and the transcripts of clips with speech; open a single contact
   sheet only for a real doubt.
3. One message: what the footage holds, what is missing, and the video plan: how many videos, **in which shapes and
   for which platforms**, lengths, which recaps go where. **Stop.**

**4 · Questions, facts, story plan.** For all the trip's videos together: one real-viewer interview, one fact sheet
(`work/references.md`: what was said on camera and will be used), one **story plan** per video
(`references/story-and-lines.md`; one page in `work/story/<video>.md`). **Stop.** The order is settled here, on
paper, before any cutting.

**5 · Lines to re-record.** Only what step 4 says the footage lacks, plus each short's outline, in one file, written
from the director's own sentences. **Stop.**

**6 · Re-record and intake.** One session, same microphone as the recaps. `footage_index.py` (new files only),
`word_index.py`, and `vlog_qalign.py` when the `align` part is installed. **Stop only if** a fact changed, a line is
missing or a take needs choosing.

**7 · First cut (checking copy).** Voice and footage with subtitles; `vlog_run.py <trip> <ids>`. The long video and
its short together. The director watches on the **review page** and edits on the **editing page**
(`vlog_editor.py`, http://localhost:8765). **Stop.** Story and pacing are locked here.

**8 · Cut with music.** Music plan, privacy pass (`work/privacy.json`), place tags, end card. Send the cut with the
plan. **Stop.** Sound-only notes: remix only, no rebuild.

**9 · Final and package.** Translated subtitles, `vlog_run.py <trip> <ids> --final`, `vlog_srt.py`, covers and
thumbnails (ideas first, as text), `vlog_platform.py check` for every platform, then the upload package: one section
per platform, each with its own text (`references/platforms.md`). **Stop.** The director uploads and schedules.
Finally, write in `CHANNEL.md` what to do better next trip.

## Whole trip together, then pair by pair
Steps 1–5 are done once for the whole trip. From the first cut on, work goes **pair by pair**: one long video with
its short, reviewed, fixed, confirmed and rendered before the next pair. Aim for two review rounds per pair.

## Don't do it twice
| Work | Done once at | Afterwards |
|---|---|---|
| Transcripts, contact sheets, 720p copies | step 3 | never re-run; read from `work/` |
| Looking at footage | mosaics first | a single sheet only for a real doubt |
| Viewer interview, fact sheet | step 4, all videos in one go | later steps check only new wording |
| Re-recording | step 6, one session per trip | pick-ups only for a fact error |
| Translation | step 9 | never before the cut is fixed |
| Rendering | only changed shots are redone | sound notes never rebuild video; the final only at step 9 |
| Thumbnails, texts | step 9 | never before the final |

## Rendering and checks
- **Render only with `vlog_run.py <trip> <ids> [--final]`**: self-test → edit-list check → what the director's
  edits changed and anything they broke (CHANGE / WARN) → faces (when the `privacy` part is installed; otherwise it
  says SKIPPED every time and you look at passers-by yourself) → on-screen text against the approved stills → the
  build under a stall watchdog → picture check. One render at a time on a computer.
- Tell the director every WARN and every face question in plain words before rendering; record their answers
  (`vlog_precheck.py <trip> <id> --accept "<words>"`, `work/privacy.json`) so nothing is asked twice.
- Clips and times the director names go through `vlog_pick.py` first (shake, too short, used already).
- After a final: `vlog_sharp.py` shows the softest shots at full size. A soft shot is told to the director with
  its time, never rescued in the edit.
- Sizes and margins live in `vlog_layout.py` only. After changing any script: `vlog_selftest.py`.
