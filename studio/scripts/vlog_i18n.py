"""English for the review page and the editing page ([ui] language = "en" in vlog.toml; "zh" keeps the Chinese they
were written in). Each known phrase is replaced by its English, longest first; values and code pass through.
The cut marks themselves are not translated: 〔 〕 and [ ] both mean "cut this voice", ( ) is a note to the editor.
"""
import vlog_env

EN = {
    # ---------------- review page
    "空格＝播放 / 暂停 · ← →＝退 / 进 2 秒（按住 Shift 是 0.5 秒）· ↑ ↓＝上一个 / 下一个镜头 · , .＝一格一格 · 1–9、0＝点第几个意见 · E＝去字幕剪辑页的这一句":
        "Space = play / pause · ← → = back / forward 2 s (with Shift: 0.5 s) · ↑ ↓ = previous / next shot · , . = frame by frame · 1–9, 0 = that note · E = this line on the editing page",
    "连不上审片程序（它被关掉了）。笔记还在这一页：先别关这一页，请 Claude 重新打开程序后再点一下任何按钮，就会存。":
        "The review program cannot be reached (it was closed). Your notes are still on this page: keep it open, ask Claude to start the program again, then tap any button and they are saved.",
    "暂停在有问题的地方 → 点上面的按钮（或按数字键）。会自动记下时间、是哪个镜头、在讲哪句。笔记自动保存。":
        "Pause where something is wrong → tap a button above (or press its number). The time, the shot and the line being said are noted for you. Notes save by themselves.",
    "去字幕剪辑页，同一支影片、现在讲到的这一句（键盘 E）": "to the editing page: the same video, the line being said now (key E)",
    "想多说一句就打在这里（可以不打），Enter 存好": "Type here if you want to add a word (optional), Enter saves it",
    "工具已更新：保存现在的修改后，页面会自动重新载入。": "The tools were updated: once your changes are saved, the page reloads by itself.",
    "还没有笔记。暂停在有问题的地方，点上面的按钮。": "No notes yet. Pause where something is wrong and tap a button above.",
    "还有没保存的修改，确定换别的旅行吗？": "There are unsaved changes. Switch to another trip anyway?",
    "键盘（跟棚拍的审片页一样）：": "Keys: ",
    "有 ${shortN} 个镜头短于 2 秒（红框）": "${shortN} shot(s) are shorter than 2 s (red frame)",
    "工具已更新，已重新载入": "tools updated, page reloaded",
    "字幕剪辑（这一句）↗": "edit this line ↗",
    "还没有手机版可以看": "no checking copy to watch yet",
    "有我的提示声/人声": "my own cue / voice in it", "这里让旁白停一下": "let the voice pause here", "画面跟讲的不对": "picture does not match the words",
    "声音画面不同步": "sound and picture out of sync", "跟前一个太像": "too like the one before", "停顿放错地方": "pause in the wrong place",
    "换别的镜头": "use another shot", "再长一点": "a little longer", "字幕有错": "subtitle wrong", "事实要查": "check this fact",
    "要打码": "blur this", "镜头晃": "shaky", "太长": "too long", "太短": "too short", "其他": "other",
    "（原片从 ${s.src.toFixed(1)} 秒）": " (from ${s.src.toFixed(1)} s of the clip)",
    "（第 ${k + 1} 个镜头，${s.d.toFixed(1)} 秒）": " (shot ${k + 1}, ${s.d.toFixed(1)} s)",
    '" · 原片 " + n.src.toFixed(1) + " 秒"': '" · clip at " + n.src.toFixed(1) + " s"',
    "${s.d.toFixed(1)} 秒`": "${s.d.toFixed(1)} s`",
    "这一支的笔记": "Notes on this video", "这一版：": "this build: ", "删掉这条": "delete this note", "← 很短": "← very short",
    "没存到！": "not saved!", "记下了": "noted", "${list.length} 条": "${list.length} note(s)",
    "审片 · ${d.trip}": "Review · ${d.trip}", "<title>审片</title>": "<title>Review</title>", "<h1>审片</h1>": "<h1>Review</h1>",
    # ---------------- editing page
    "暗的部分＝影片里没有 · 拖一段 → 空格听 → X：亮的剪掉、暗的放回（字幕里没有的嗯、啊，被剪掉的字尾都能处理）· 点暗处选那一段 · 点亮处从那里播放 · 点你剪的（红 ✂）或放回的（绿线）选它，Delete 取消它":
        "Dark = not in the video · drag a stretch → Space to hear it → X: bright is cut, dark is put back (an um the subtitles do not hold, a word end that was cut off) · click a dark part to select it · click a bright part to play from there · click one of your cuts (red ✂) or put-backs (green line) to select it, Delete undoes it",
    "连不上剪辑程序（它被关掉了）。你的修改还在这一页：先不要重新载入页面，请 Claude 重新打开程序，再按一次保存。":
        "The editing program cannot be reached (it was closed). Your changes are still on this page: do not reload it; ask Claude to start the program again, then press Save once more.",
    "〕Whisper 没听到，自动剪可能不准（会连旁边的字一起剪）：请在下面的声音图上把它拖出来按 X 剪掉。字幕里的〔〕留着没关系":
        "〕 was not heard by the speech model, so the automatic cut may be off (it can take a neighbouring word with it): drag over it on the waveform below and press X. The 〔〕 in the subtitle can stay",
    "的词＝听得到但字幕里没有，点一下写进字幕。灰色的词勾「听原声」能听到，点一下就放回影片（点绿色的＋字可以改字） ·":
        " words = heard but not in the subtitle: click one to write it in. Grey words can be heard with “hear the recording” ticked: click one to put it back into the video (click a green ＋ word to change its text) ·",
    "」没剪：影片里还会显示（接在上一句字幕后面）。要整句删掉，按 🗑 删整句（Delete）": "” is not cut: it will still show (joined to the subtitle before). To remove the whole line, press 🗑 Delete line (Delete)",
    "这一句回到程序自动做的样子：字幕改回自动的字，你在这一句里按时间剪的、放回的都取消": "This line goes back to what the program made: the automatic text, and every cut or put-back you made in it by time is undone",
    "整句删掉了（字幕和声音）。再按一次 Delete 还原，或 Ctrl+Z": "Whole line removed (subtitle and voice). Delete again brings it back, or Ctrl+Z",
    "选了你剪掉的这一段：Delete 取消这个剪辑（回到自动），空格听原声": "Your cut is selected: Delete undoes it (back to automatic), Space plays the recording",
    "＝跟上一条接成一条（不同录音、中间隔一行、拖不过去的时候用） ·": " = join it to the subtitle before (for another recording, a line in between, or when dragging will not reach) ·",
    "取消了你剪的这一段（回到自动）。如果还是暗的，再按一次 X 放回": "Your cut here is undone (back to automatic). If it is still dark, press X again to put it back",
    "选了你放回的这一段：Delete 取消放回（回到自动），空格听": "Your put-back is selected: Delete undoes it (back to automatic), Space plays it",
    "让程序检查每一句：有没有字被剪掉、剪的字还听得到、声音不见了": "Check every line: a kept word that cannot be heard, a cut word that still can, voice that went missing",
    "放回影片的词（点一下改字）：保存后下次出片会加进影片和字幕": "Words put back into the video (click to change the text): after saving, the next build adds them to the sound and the subtitle",
    "这些词在字幕里没有对应的字：先在字幕里把它们打出来，再剪": "These words have no text in the subtitle: type them into the subtitle first, then cut",
    "（或 ／）＝在这里分成两条字幕，可以用几次分成几条 ·": " (or ／) = split into two subtitles here; use it several times for several ·",
    " · 影片里听得到，但字幕里没有这个词。点一下写进字幕": " · heard in the video but not in the subtitle. Click to write it in",
    "Delete：整句的字幕和声音都剪掉（再按一次还原）": "Delete: remove the whole line, subtitle and voice (press again to bring it back)",
    "这一句还原成自动的样子了（Ctrl+Z 可以反悔）": "This line is back to automatic (Ctrl+Z undoes that)",
    "改字，Enter 确定（〔〕里的字＝剪掉） ·": " to change the text, Enter confirms (text inside 〔〕 or [ ] = cut) ·",
    "选了影片里没有的这一段：按 X 放回，空格听": "A stretch that is not in the video is selected: X puts it back, Space plays it",
    "先在声音图上拖一段暗的地方，再按 R 放回去": "Drag over a dark stretch on the waveform first, then press R to put it back",
    "下面的小词选它（Shift+点 选一段），按": " a small word below to select it (Shift+click for a run), press",
    "去审片页，同一支影片、从选中的这一句开始看": "to the review page: the same video, from the selected line",
    "Ctrl+Y 或 Ctrl+Shift+Z": "Ctrl+Y or Ctrl+Shift+Z",
    "＝回到自动的样子 · 在声音图上拖一段：": " = back to automatic · drag on the waveform: ",
    "放回的词要显示成什么字（〔〕＝还是剪掉）": "The text the put-back words should show (〔〕 = still cut)",
    "秒 · 影片里没用到。点一下放回影片": "s · not used in the video. Click to put it back",
    "（保存后，下次出片会加进声音和字幕）": " (after saving, the next build adds it to the sound and the subtitle)",
    "还有没保存的修改，确定换别的影片吗？": "There are unsaved changes. Switch to another video anyway?",
    "这一段本来就在影片里（要剪掉按 X）": "This stretch is already in the video (press X to cut it)",
    "选好了：空格听，Delete 取消它": "Selected: Space plays it, Delete undoes it",
    "只能移到同一段录音的上一句或下一句": "A word can only move to the line before or after in the same recording",
    "秒 · 已放回影片（再点一下取消）": "s · put back into the video (click again to undo)",
    "删整句（字幕和声音，再按还原） ·": " remove the whole line (subtitle and voice; again brings it back) ·",
    "到上一句或下一句，就把它移过去 ·": " it onto the line before or after to move it there ·",
    "保存（存进字幕表，下次出片就用）": "Save (into the subtitle sheet; the next build uses it)",
    "直接播放原来的录音，什么都不跳过": "Play the recording itself, skipping nothing",
    "放回影片了（正在播前后听听看）": "Put back (playing around it so you can hear)",
    "＝给剪辑的备注，不会出现在字幕": " = a note to the editor, never shown in the subtitle",
    "${CHECK.length} 个地方请听一下（点它跳过去）": "${CHECK.length} place(s) to listen to (click to jump there)",
    "检查中…（第一次要等十几秒）": "Checking… (the first time takes ten seconds or so)",
    "这个词在字幕里没有字，移不了": "This word has no text in the subtitle, so it cannot move",
    "这一句没有自动的版本可以还原": "This line has no automatic version to go back to",
    "剪掉了（正在播前后听听看）": "Cut (playing around it so you can hear)",
    "这一句本来就是自动的样子": "This line is already as the program made it",
    "＝跟下一条接成一条，放在": " = join it to the next subtitle; at the ",
    "声音全剪了，但字幕里「${left}": "All the voice is cut, but in the subtitle “${left}",
    "整句还原了（字幕和声音）": "Whole line brought back (subtitle and voice)",
    "先点一个小词，再按 X": "Click a small word first, then press X",
    "处）。下次出片才会用上": " place(s)). The next build will use them",
    "剪掉的「$1」还听得到": "the cut “$1” can still be heard", "没剪的「$1」听不到": "the kept “$1” cannot be heard",
    "这里没有你剪的或放回的": "Nothing you cut or put back is here",
    "这句没有录音（只改字）": "This line has no recording (text only)",
    "的词＝影片里没用到；": " words = not used in the video; ",
    "（字可以点字幕再改）": " (click the subtitle to change the text)",
    "▶ 播放选中的那句": "▶ Play the selected line", "没有这段录音的声音": "no sound for this recording",
    "＝剪掉这段声音 ·": " = cut this voice ·", "文字旁白（还没录）": "text narration (not recorded yet)",
    "剪掉 / 还原 ·": " to cut / bring back ·", "取消了（回到自动）": "Undone (back to automatic)",
    "按时间剪的还听得到": "a cut made by time can still be heard", "（或 +）放在字幕": " (or +) at the ",
    "后面没有要播的声音": "No sound to play after this", "拖长一点再按 X": "Drag a little longer, then press X",
    "这里有声音不见了": "voice went missing here", "没有可以撤销的了": "Nothing left to undo", "没有可以重做的了": "Nothing left to redo",
    "小词从那里播放，": " a small word to play from there, ", "取消（回到自动）": "undo (back to automatic)",
    "字幕剪辑 · ${d.trip}": "Edit · ${d.trip}", "✂ 剪 / 还原": "✂ Cut / bring back", "播放 / 停 ·": " play / stop ·",
    "审片（这一句）↗": "review this line ↗", "↺ 还原这一句": "↺ Reset this line", "写进字幕了：${txt}": "Written into the subtitle: ${txt}",
    "听原声（不剪）": "hear the recording (uncut)", "字幕里的符号": "Marks in a subtitle", "找不到这一句": "This line cannot be found",
    "算不出剪辑：": "The cut could not be worked out: ", "＋ 你放回的": "＋ your put-back", "🔍 检查这支": "🔍 Check this video",
    "取消选取 ·": " clears the selection ·", "这句没有录音": "This line has no recording", "全部通过 ✓": "all good ✓",
    "放回影片：${": "Put back: ${", "🗑 删整句": "🗑 Delete line", "从这句播放": "play from this line", "计算剪辑…": "working out the cut…",
    "检查出错：": "the check failed: ", "已保存（${res.changed}": "Saved (${res.changed}", "全部已保存": "all saved", "载入声音…": "loading sound…",
    "只播这一句": "this line only", "✂ 你剪的": "✂ your cut", "${n} 句还没保存": "${n} line(s) not saved", "连续播放": "play on",
    "橙色虚线": "orange dashed", "灰色虚线": "grey dashed", "↶ 撤销": "↶ Undo", "↷ 重做": "↷ Redo", "保存中…": "saving…", "播放范围": "what plays",
    "保存失败": "not saved", "重做 ·": " redo ·", "录音 ${r.voice}": "recording ${r.voice}", "取消放回": "put-back undone", "载入中…": "loading…",
    "放回去，": " put back, ", "原声 ${p.voice}": "recording ${p.voice}", "<title>字幕剪辑</title>": "<title>Edit</title>", "<h1>字幕剪辑</h1>": "<h1>Edit</h1>",
    "检查中": "Checking", "（空）": "(empty)", "剪掉，": " cut, ", "撤销，": " undo, ", "■ 停": "■ Stop", "<b>点字幕</b>": "<b>click a subtitle</b>",
    "把小词<b>拖</b>": "<b>Drag</b> a small word", "<b>最前面</b>": "<b>start</b>", "<b>最后</b>": "<b>end</b>", "已更新": "updated", "已保存": "saved",
    ">保存</button>": ">Save</button>", "<b>双击</b>": "<b>Double-click</b>", 'title="旅行"': 'title="trip"', 'title="空格"': 'title="Space"',
    "<b>空格</b>": "<b>Space</b>", "<b>点</b>": "<b>Click</b>", "</b> 或 <b>": "</b> or <b>", "${w.s.toFixed(2)} 秒`": "${w.s.toFixed(2)} s`",
    'lang="zh"': 'lang="en"',
}


def page(html):
    if vlog_env.UI == "zh":
        return html
    for zh in sorted(EN, key=len, reverse=True):
        if zh in html:
            html = html.replace(zh, EN[zh])
    return html


def t(phrase):
    return phrase if vlog_env.UI == "zh" else EN.get(phrase, phrase)
