# Changelog

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
