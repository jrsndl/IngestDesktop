import os
import subprocess
import json
import logging

from logic.proc import resolve_tool, run_tool

IMAGE_EXTENSIONS = {
    ".exr", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".tga", ".dpx", ".hdr"
}

def get_ffprobe_data(path_to_file, ffprobe_exe, logger=None, timeout=6.0):
    """Get metadata via ffprobe."""
    if timeout == 0 or timeout == 0.0:
        timeout = None

    if logger is None:
        logger = logging.getLogger(__name__)

    ffprobe_exe = resolve_tool(ffprobe_exe)
    if not ffprobe_exe:
        logger.warning("FFprobe not found (check Preferences > Conversions > ffprobe path)")
        return {}

    args = [
        ffprobe_exe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        path_to_file
    ]

    try:
        result = run_tool(args, timeout=timeout)
        return json.loads(result.stdout)
    except Exception as e:
        logger.error(f"Failed to get ffprobe data for {path_to_file}: {e}")
        return {}

def get_oiio_info_for_input(path_to_file, oiiotool_exe, logger=None, timeout=6.0):
    """Get metadata via oiiotool."""
    if timeout == 0 or timeout == 0.0:
        timeout = None

    if logger is None:
        logger = logging.getLogger(__name__)

    oiiotool_exe = resolve_tool(oiiotool_exe)
    if not oiiotool_exe:
        logger.warning("OIIOTool not found (check Preferences > Conversions > oiiotool path)")
        return {}

    # oiiotool doesn't have a direct JSON output for info in older versions
    # but we can parse the verbose output or use specific formatting if available.
    # For now, let's try a simple approach or look for --info:format json
    
    args = [
        oiiotool_exe,
        "--info:format=xml", "-v",
        path_to_file
    ]

    try:
        result = run_tool(args, timeout=timeout)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(result.stdout)
        
        output = {"attribs": {}}
        # The XML usually has ImageSpec as the root or under a top-level element
        # We'll look for common tags
        spec = root.find(".//ImageSpec")
        if spec is None:
            spec = root # Try root if ImageSpec not found
            
        for child in spec:
            if child.tag == "attrib":
                name = child.get("name")
                if name:
                    val = child.text
                    if "smpte:" in name.lower():
                        name = name.split(":", 1)[-1]
                    output["attribs"][name] = val
                    output[name.lower()] = val
            else:
                output[child.tag.lower()] = child.text
            
        return output
    except Exception as e:
        logger.error(f"Failed to get OIIO info for {path_to_file}: {e}")
        return {}

def is_oiio_supported(oiiotool_exe):
    return oiiotool_exe and os.path.exists(oiiotool_exe)

def parse_rate(value):
    """'24000/1001' -> 23.976..., '25' -> 25.0, '0/0' or junk -> None."""
    if value is None:
        return None
    s = str(value).strip()
    try:
        if "/" in s:
            num, den = s.split("/", 1)
            num, den = float(num), float(den)
            return num / den if den else None
        v = float(s)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def timecode_to_frames(tc, fps):
    """SMPTE timecode -> frame number.

    Uses the nominal (rounded) rate, as timecode does: 01:00:00:00 @ 23.976 = 86400.
    A ';' or '.' before the frames field marks drop-frame (29.97 / 59.94).
    """
    tc = str(tc).strip()
    drop = ";" in tc or tc.count(".") == 1 and ":" in tc
    parts = tc.replace(";", ":").replace(".", ":").split(":")
    if len(parts) != 4:
        return None
    h, m, s, f = (int(p) for p in parts)
    nominal = int(round(float(fps)))
    if nominal <= 0:
        return None
    total = ((h * 3600) + (m * 60) + s) * nominal + f
    if drop and nominal in (30, 60):
        drop_frames = 2 if nominal == 30 else 4
        total_minutes = h * 60 + m
        total -= drop_frames * (total_minutes - total_minutes // 10)
    return total


def get_image_info_metadata(path_to_file, ffprobe_exe, oiiotool_exe, keys=None, logger=None, timeout=6.0):
    """Get flattened metadata from image file.
    
    Based on ayon-core implementation.
    """
    if timeout == 0 or timeout == 0.0:
        timeout = None

    if logger is None:
        logger = logging.getLogger(__name__)

    def _ffprobe_metadata_conversion(metadata):
        output = {}
        if not metadata: return output
        for key, val in metadata.items():
            k_low = key.lower()
            if k_low in ("tags", "disposition") and isinstance(val, dict):
                for sub_k, sub_v in val.items():
                    output[sub_k.lower()] = sub_v
            else:
                output[k_low] = val
        return output

    def _get_video_metadata_from_ffprobe(ffprobe_stream):
        video_stream = None
        for stream in ffprobe_stream.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break
        out = _ffprobe_metadata_conversion(video_stream)
        # MOV/MXF often keep the timecode in a tmcd/data stream or the container tags
        if "timecode" not in out:
            for stream in ffprobe_stream.get("streams", []):
                tc = (stream.get("tags") or {}).get("timecode")
                if tc:
                    out["timecode"] = tc
                    break
        if "timecode" not in out:
            tc = ((ffprobe_stream.get("format") or {}).get("tags") or {}).get("timecode")
            if tc:
                out["timecode"] = tc
        fmt_dur = (ffprobe_stream.get("format") or {}).get("duration")
        if "duration" not in out and fmt_dur:
            out["duration"] = fmt_dur
        return out

    metadata_stream = None
    ext = os.path.splitext(path_to_file)[-1].lower()
    
    # Try OIIO first for supported images
    if ext in IMAGE_EXTENSIONS and is_oiio_supported(oiiotool_exe):
        oiio_stream = get_oiio_info_for_input(path_to_file, oiiotool_exe, logger=logger, timeout=timeout)
        if "attribs" in (oiio_stream or {}):
            metadata_stream = {}
            for key, val in oiio_stream["attribs"].items():
                if "smpte:" in key.lower():
                    key = key.replace("smpte:", "")
                metadata_stream[key.lower()] = val
            for key, val in oiio_stream.items():
                if key == "attribs":
                    continue
                metadata_stream[key] = val
    
    # Fallback to FFprobe if OIIO failed or extension not supported
    if not metadata_stream:
        ffprobe_stream = get_ffprobe_data(path_to_file, ffprobe_exe, logger, timeout=timeout)
        if "streams" in ffprobe_stream and len(ffprobe_stream["streams"]) > 0:
            metadata_stream = _get_video_metadata_from_ffprobe(ffprobe_stream)

    if not metadata_stream:
        logger.warning(f"Failed to get metadata from file: {path_to_file}")
        return {}

    # Extract framerate
    # avg_frame_rate is the real rate; r_frame_rate can be a field/timebase rate
    for rate_key in ("avg_frame_rate", "r_frame_rate", "framespersecond"):
        rate = parse_rate(metadata_stream.get(rate_key))
        if rate:
            metadata_stream["framerate"] = rate
            break

    # Ensure width and height are integers
    for key in ["width", "height"]:
        if key in metadata_stream:
            try:
                metadata_stream[key] = int(metadata_stream[key])
            except (TypeError, ValueError):
                pass

    # Calculate start_from_tc if possible
    if "timecode" in metadata_stream and "framerate" in metadata_stream:
        tc = str(metadata_stream["timecode"])
        try:
            start_frame = timecode_to_frames(tc, metadata_stream["framerate"])
            if start_frame is not None:
                metadata_stream["start_from_tc"] = start_frame
        except (TypeError, ValueError) as e:
            logger.warning(f"Cannot read timecode '{tc}': {e}")

    # Calculate nb_frames (total frame count) if missing but duration/fps exist
    if "nb_frames" not in metadata_stream:
        if "duration" in metadata_stream and "framerate" in metadata_stream:
            try:
                dur = float(metadata_stream["duration"])
                fps = float(metadata_stream["framerate"])
                # Rounding or int() is usually correct for CFR
                metadata_stream["nb_frames"] = int(round(dur * fps))
            except Exception:
                pass

    if keys is None:
        return metadata_stream

    output = {}
    for key in keys:
        if key in metadata_stream:
            output[key] = metadata_stream[key]
    
    return output
