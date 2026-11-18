"""Subtitle sheets as Excel files the director can edit (a plain .tsv turns into a mess in a text editor).

The build keeps writing <id>.tsv (machine copy) and also writes <id>.xlsx beside it. When the .xlsx is newer than the .tsv,
the build reads the director's edits from the .xlsx.
Usage: python vlog_sheet.py <subtitles folder>      makes an .xlsx for every .tsv that has none, or an older one
"""
import sys
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

import vlog_env  # noqa: E402

HEAD = (["视频时间", "编号（别改）", "Whisper 原文（听到的）", "字幕（改这里；要剪掉的声音用〔〕括起来）", "提醒", "自动（别改）"] if vlog_env.UI == "zh" else
        ["Time in the video", "Id (do not change)", "As heard (Whisper)", "Subtitle (edit here; put voice to cut in [ ])", "Note", "Automatic (do not change)"])
WIDTH = [10, 14, 44, 52, 26, 10]


def write_xlsx(path, rows):
    """rows: lists of 6 strings, without the header."""
    wb = Workbook()
    ws = wb.active
    ws.title = vlog_env.tr("Subtitles", "字幕")
    ws.append(HEAD)
    for r in rows:
        ws.append([str(x) for x in r] + [""] * (6 - len(r)))
    font = Font(name="Microsoft YaHei", size=12)
    edit = PatternFill("solid", fgColor="FFF4C2")
    new = PatternFill("solid", fgColor="DDEBFF")
    for i, w in enumerate(WIDTH):
        ws.column_dimensions["ABCDEF"[i]].width = w
    ws.column_dimensions["B"].hidden = True
    ws.column_dimensions["F"].hidden = True
    for row in ws.iter_rows():
        for c in row:
            c.font = Font(name="Microsoft YaHei", size=12, bold=c.row == 1)
            c.alignment = Alignment(wrap_text=True, vertical="top")
        if row[0].row > 1:
            row[3].fill = new if row[2].value == "（新旁白）" else edit
    ws.freeze_panes = "A2"
    wb.save(path)


def read_xlsx(path):
    wb = load_workbook(path, read_only=True)
    try:
        out = []
        for i, r in enumerate(wb.active.iter_rows(values_only=True)):
            if i == 0:
                continue
            out.append(["" if v is None else str(v) for v in (list(r) + [None] * 6)[:6]])
        return out
    finally:
        wb.close()     # read-only workbooks keep the file open; an open handle stops Excel from saving it


def read_tsv(path):
    return [line.split("\t") for line in path.read_text(encoding="utf-8-sig").splitlines()[1:]]


def rows_for_edits(tsv):
    """The rows to read edits from: the .xlsx when the director saved it after the build wrote the .tsv."""
    x = tsv.with_suffix(".xlsx")
    if x.exists() and x.stat().st_mtime > tsv.stat().st_mtime + 1:
        return read_xlsx(x)
    return read_tsv(tsv)


if __name__ == "__main__":
    for t in sorted(Path(sys.argv[1]).glob("*.tsv")):
        x = t.with_suffix(".xlsx")
        if not x.exists() or x.stat().st_mtime < t.stat().st_mtime:
            write_xlsx(x, read_tsv(t))
            print(x.name)
