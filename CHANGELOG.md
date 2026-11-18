# Changelog

## 1.0.1 (2026-11-18)
- Subtitle files are named `subtitles.<language>_<COUNTRY>.srt` and `short.<language>_<COUNTRY>.srt`: Facebook accepts
  no other shape.
- Cover rules: the presenter may be on a short cover (cut out and layered, words never on them), ideas as text
  first, one file for the Shorts thumbnail and the Reels cover.
- Platform rules read on the platforms' help pages (2026-11): YouTube thumbnails (3840×2160 recommended, 2 MB from a
  phone, 50 MB from a computer), Shorts thumbnails, Instagram Reels (up to 20 minutes, not recommended to new
  audiences past 3), TikTok (uploads up to 60 minutes), Facebook's subtitle file names and its list of accepted
  language codes. Each block of `platforms.toml` now says what was verified. 小红书 and 哔哩哔哩 are unverified.

## 1.0.0 (2026-11-18)

First public version: the vlog and site-visit pipeline as it runs today, opened up for any channel.

- Setup checks the computer first (`probe.py`) and estimates the time of every step, with 1080p and 4K finals side by
  side; asks whether the channel makes horizontal videos, vertical ones or both, which platforms it posts to, and
  whether filming is on a camera or a phone.
- Every part is explained and asked about before it is installed (`setup_studio.py`): core, fonts, speech recognition
  (three model sizes), privacy, music fitting, thumbnail cut-out, precise word timing. Parts can be removed again.
- Footage index with transcripts, contact sheets, one overview picture per place, shake and sharpness per second.
- A path for footage that already exists: placing unsorted clips, a recap recorded afterwards.
- Edit lists built from a story plan; one gate for every render (`vlog_run.py`) with a self-test, edit check,
  side-effect check, face check, on-screen-text check, a rehearsal before finals and a stall watchdog.
- Review page (notes by tapping) and word-level editing page with a waveform, in English or Chinese.
- Steadying, brightness levelling, tracked blur, music fitted on bar lines, subtitle files with translations.
- Platform rules in one editable file and a checker for finished files (`vlog_platform.py`).
- `vlog_new.py` for trips and videos in the shapes the channel makes.
