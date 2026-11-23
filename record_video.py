"""Film the visible game client at one video frame per TAS frame."""
import argparse
from contextlib import closing
import ctypes as ct
from ctypes import wintypes as wt
from itertools import groupby
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from client import call

user32, gdi32 = ct.windll.user32, ct.windll.gdi32
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.GetClientRect.argtypes = [wt.HWND, ct.POINTER(wt.RECT)]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.CreateDIBSection.argtypes = [wt.HDC, ct.c_void_p, wt.UINT, ct.POINTER(ct.c_void_p), wt.HANDLE, wt.DWORD]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.BitBlt.argtypes = [wt.HDC, ct.c_int, ct.c_int, ct.c_int, ct.c_int, wt.HDC, ct.c_int, ct.c_int, wt.DWORD]


class BITMAPINFOHEADER(ct.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class Grabber:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        rect = wt.RECT()
        user32.GetClientRect(hwnd, ct.byref(rect))
        self.width, self.height = rect.right - rect.left, rect.bottom - rect.top
        self.width -= self.width % 2
        self.height -= self.height % 2
        screen = user32.GetDC(hwnd)
        self.dc = gdi32.CreateCompatibleDC(screen)
        info = BITMAPINFOHEADER(ct.sizeof(BITMAPINFOHEADER), self.width, -self.height, 1, 32, 0, 0, 0, 0, 0, 0)
        self.bits = ct.c_void_p()
        self.bitmap = gdi32.CreateDIBSection(self.dc, ct.byref(info), 0, ct.byref(self.bits), None, 0)
        self.previous = gdi32.SelectObject(self.dc, self.bitmap)
        user32.ReleaseDC(hwnd, screen)
        self.size = self.width * self.height * 4

    def grab(self):
        # BitBlt from the window's own DC, as FFmpeg's gdigrab does. PrintWindow returned black frames
        # for the game's Direct3D 9 surface (tried 2026-11-23). The window has to be visible on screen.
        source = user32.GetDC(self.hwnd)
        try:
            if not gdi32.BitBlt(self.dc, 0, 0, self.width, self.height, source, 0, 0, 0x00CC0020 | 0x40000000):
                raise OSError("BitBlt failed")          # SRCCOPY | CAPTUREBLT
        finally:
            user32.ReleaseDC(self.hwnd, source)
        return ct.string_at(self.bits, self.size)

    def close(self):
        gdi32.SelectObject(self.dc, self.previous)
        gdi32.DeleteObject(self.bitmap)
        gdi32.DeleteDC(self.dc)


def ass_time(frame):
    cs = frame * 100 // 60
    return f"{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}"


def subtitles(keys):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Keys,Arial,32,&H00FFFFFF,&H00FFFFFF,&H00000000,&H60000000,0,0,0,0,100,100,0,0,1,2,1,1,24,24,24,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines, start = [], 0
    for value, group in groupby(keys):
        end = start + sum(1 for _ in group)
        if value:
            label = re.sub(r"([{}\\])", r"\\\1", value)
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Keys,,0,0,0,,{label}\n")
        start = end
    return header + "".join(lines)


def encode(grabber, folder, first, last, keys):
    filters = []
    if keys is not None:
        (folder / "keys.ass").write_text(subtitles(keys), encoding="utf-8")
        filters = ["-vf", "subtitles=keys.ass"]
    args = ["ffmpeg", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra",
            "-s", f"{grabber.width}x{grabber.height}", "-r", "60", "-i", "-", *filters,
            "-c:v", "h264_nvenc", "-preset", "p7", "-cq", "16", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "video.mp4"]
    with subprocess.Popen(args, stdin=subprocess.PIPE, cwd=folder) as video:
        for frame in range(first, last+1):
            if frame != first:
                call("step", count=1)
            video.stdin.write(grabber.grab())
        video.stdin.close()
        if video.wait():
            raise RuntimeError(f"FFmpeg exited with {video.returncode}")


def record(script, out, first=0, last=None, show_keys=False):
    frames = call("load", path=str(script.resolve()))["frames"]
    last = frames if last is None else last
    if not 0 <= first <= last <= frames:
        raise ValueError("Invalid recording frame range")
    keys = None
    if show_keys:
        keys = [" + ".join(row) for row in call("timeline-keys", first=first, last=last)]
    state = call("status")
    call("goto", count=first)
    with TemporaryDirectory(dir=out.parent) as temp, closing(Grabber(int(state["gameWindow"], 16))) as grabber:
        folder = Path(temp)
        encode(grabber, folder, first, last, keys)
        (folder / "video.mp4").replace(out)
    return str(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("first", nargs="?", type=int, default=0)
    parser.add_argument("last", nargs="?", type=int)
    parser.add_argument("--keys", action="store_true")
    a = parser.parse_args()
    record(a.script, a.out, a.first, a.last, a.keys)
