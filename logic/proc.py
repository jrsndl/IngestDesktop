"""Running external tools (ffmpeg, ffprobe, oiiotool) safely on Windows.

* tool paths may be a bare name on PATH ("ffprobe.exe") or a full path
* no console window flashes up
* output is decoded as UTF-8 (never the Windows ANSI code page)
* stdin is closed, so a tool can never wait for an answer (e.g. "overwrite? [y/N]")
* a timeout per call kills the process instead of hanging a worker forever
"""
import os
import shutil
import subprocess

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def resolve_tool(path):
    """Full path of a tool, or None if it cannot be found."""
    if not path:
        return None
    path = os.path.expandvars(path.strip().strip('"'))
    if os.path.isfile(path):
        return path
    found = shutil.which(path)
    return found


def run_tool(args, timeout=None, text=True):
    """subprocess.run with the safe defaults above. Raises like subprocess.run(check=True)."""
    if timeout is not None and timeout <= 0:
        timeout = None
    kwargs = dict(capture_output=True, check=True, timeout=timeout,
                  stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
    if text:
        kwargs.update(text=True, encoding="utf-8", errors="replace")
    return subprocess.run(args, **kwargs)
