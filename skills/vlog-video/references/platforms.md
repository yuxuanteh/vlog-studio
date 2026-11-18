# Platforms: what differs, and the upload package

The channel's platforms are in `[platforms] post_to` (vlog.toml) and `CHANNEL.md`. The numbers (lengths, sizes,
character limits) are in `<studio>/platforms.toml`. Each block says the month it was last read on the platform's own
help page (`checked`) and which of its lines that reading covered (`verified`); the rest is general knowledge.

**Platforms change their rules often.** Before a limit decides something (a video cut to fit a length, a link left
out), open that platform's own help page, and correct `platforms.toml` and its `checked` month. Say when a rule
you relied on could not be checked.

`python scripts/vlog_platform.py check <final.mp4> [--cover cover.png] [--text caption.txt]` checks a finished file
against every platform the channel posts to that takes its shape. Run it on every final.

## What usually differs (read the file for the current numbers)
| | Long video (YouTube, 哔哩哔哩) | Vertical (YouTube Shorts, Instagram Reels, Facebook Reels, TikTok, 小红书) |
|---|---|---|
| Shape | 16:9 | 9:16 |
| Length | long is fine | each platform has its own upper limit, and shorter usually travels further |
| Links in the text | can be clicked | mostly cannot: point to the profile, or name the long video |
| Cover | a 16:9 thumbnail with a file-size limit | the cover is cropped in profile grids: words and faces inside the safe box |
| On-screen buttons | none over the picture | the bottom and the right edge are covered: subtitles and words stay clear of them |
| Chapters, end screen | yes | no |
| Music | the video's own | a track from one platform's library may be muted or blocked on another |
| Subtitles | files per language can be uploaded | burned in; the platform may add its own captions on top |

## One picture file, one text per platform
A vertical video is rendered once and posted to several platforms; a long video only where 16:9 belongs. The
**text** is written per platform, in that platform's habits:
- **YouTube (long):** one title; description = two hook lines (search shows only these), what the video covers,
  chapters (first 00:00, at least three, each 10 s or longer), sources, links, music credit, three hashtags.
- **YouTube Shorts:** a title that is the question; a short description without links; the related long video
  attached in the upload settings.
- **Instagram Reels:** the first line of the caption is all that shows before "more": make it the hook. No link
  (say "link in profile"). A few hashtags that fit, at the end.
- **Facebook Reels:** the same picture; a caption that reads like a post to friends; a link may go in the first
  comment.
- **TikTok:** a short caption, a few hashtags, no link. Upload the clean file, never a copy saved from another app
  (its watermark holds the video back).
- **小红书:** a short title, a caption written as a note with the practical details people save a post for
  (where, when, how much), no outside links or other platforms' names.
- **哔哩哔哩:** a title, a description, tags and a category; its own 16:10 cover.
For a platform that is not listed: ask the director how posts look there, and add a block to `platforms.toml`.

Write every text the way the director talks (`voice-examples.md`, their recaps): first person, their sentences, no
hype, no symbols at the start of lines, few or no emoji. Translations follow the translation rule and are written
after the cut is fixed.

## Covers and thumbnails
- Long video: 16:9 thumbnail, as large as the file-size limit allows (YouTube recommends 3840×2160 and takes 2 MB
  from a phone, 50 MB from a computer), readable at phone size.
- Vertical: a 1080×1920 cover; **the profile grid crops it**, so words and faces go inside the centred safe box
  (`cover_safe`, 1080×1350). **One file is both the YouTube Shorts thumbnail and the Reels cover**, and serves
  every other vertical platform too.
- The presenter may be on it: cut out and layered over the picture, words never on them; a cover without them is
  fine when the place carries it. Ideas first as text; made after the director's pick (editing.md "Thumbnails and
  covers").

## The upload package: `<trip>/videos/<video>/publish/publish.md`
One section per platform the channel posts to, in the order the director uploads, each complete in itself so they
paste from top to bottom:
1. the file to upload and its cover;
2. title / caption / description, copy-ready, in that platform's form;
3. settings worth setting there (playlist or series, related video, audience, location tag, who can comment);
4. subtitles: which files to upload, or "burned in". Subtitle files are named `subtitles.<language>_<COUNTRY>.srt`
   / `short.<language>_<COUNTRY>.srt`: Facebook takes them only with such names (list the short's files under each
   Reel for Facebook), YouTube takes the same files;
5. the result of `vlog_platform.py check` for that platform, and anything it warned about;
6. when to post, if the director has a plan (their plan is a record, never a deadline).
At the end: the sources behind what is said, the music used with its credit lines, and a line on anything that
differs between the platforms' versions. The director uploads and schedules by hand; nothing is posted for them.

## After posting
The director sends the links: add them to `decisions.md`, add the music to the used-list with the date, and note
in `CHANNEL.md` what each platform did with the video if they tell you (it shapes the next story plan).
