# Starting from footage that already exists

"I have footage from last year's trip, make a video." No plan, no shot list, often no recaps, sometimes one folder
of everything. The pipeline starts at step 3; this page is what changes.

## 1 · Take stock before promising anything
`vlog_new.py trip <name>`, the footage into `raw/` (copied, never moved; sub-folders exactly as the director has
them), then `footage_index.py`, `footage_proxy.py`, `clip_score.py`, `clip_motion.py`, `photo_mosaic.py`.
Read the mosaics and the transcripts and tell the director plainly what there is:
- how much footage, from when to when, in which shapes (horizontal, vertical, mixed) and sizes;
- how much of it has their voice, and what they talk about;
- what is strong (a place filmed well, a moment with a turn in it) and what is thin or missing (no wide shot, no
  arrival, sound lost to wind);
- which videos this footage can honestly become, in which shapes, and which it cannot.
**Stop** on that message. A weak video is worse than a short good one: say so.

## 2 · Placing clips the director can no longer place
When they only know the city, place clips in this order, strongest clue first:
1. **Phone photos and videos of the same days**: they carry the time and the place. A camera clip filmed minutes
   from a phone photo was filmed at that place (check the camera clock's offset against one clip they can place).
2. **Time gaps**: clips close together are one stop; a gap of half an hour or more is usually a move.
3. **Writing in the picture**: station names, street signs, tickets, shop fronts.
4. **Landmarks recognised by looking**, each with how sure you are.
Then one sheet of proposed groups with a frame from each; the director corrects only the ones marked unsure. The
grouping goes into `work/labels.csv` (`<file>,<place>` per line) and the index is run again. Nothing in `raw/` is
moved.

## 3 · No voice, or not enough
The story still comes from the director, not from you. In order of preference:
1. **A recap now.** Show them the mosaics, day by day, and ask them to talk for a few minutes per day into the
   microphone: what happened here, what surprised you, what went wrong. Memory comes back with the pictures. This
   recording is treated exactly like an evening recap (`word_index.py`), and it is usually the best narration a
   footage-only video can have.
2. **Written lines they record**, from what they tell you in the chat and what the transcripts hold
   (story-and-lines.md "Lines to re-record"). Only after their own telling.
3. **No voice at all**: a video on music and the place's own sound, with a few lines of text on screen. It works
   for one or two minutes, rarely longer: propose a vertical short or a short montage, not a ten-minute vlog.
Never invent what they felt or what happened. A fact about a place that they did not say needs a source like any
other (the fact sheet, `work/references.md`).

## 4 · Mixed footage
- **Horizontal and vertical clips together:** decide the shape of each video first. Cropping a clip to the other
  shape (`%` in the edit list sets where the crop sits) loses most of the picture: use it for a few shots, not a
  whole video, and look at each cropped frame.
- **Different cameras and phones:** frame rates and colours differ. Working copies are made at one frame rate;
  brightness is levelled between shots (when the channel has that on); colours are not matched: order the shots
  so that a camera change falls on a change of place.
- **Old low-resolution clips:** they stay at their size on a larger frame only as an inset; enlarged they are soft.
  Say which ones, and plan the final size around what most of the footage is.
- **Clips others filmed, or music in the background:** ask whose they are before using them.

## 5 · Then the normal flow
From step 4 of the skill: viewer questions, facts, **the story plan**, lines if any, first cut, review, music,
final, package. The story plan matters even more here: with no shot list behind the footage, it is the only place
where "what is this video about" gets decided before work is spent on a cut.
