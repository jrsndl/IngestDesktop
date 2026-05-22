import os
import subprocess
import json
import logging

IMAGE_EXTENSIONS = {
    ".exr", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".tga", ".dpx", ".hdr"
}

def get_ffprobe_data(path_to_file, ffprobe_exe, logger=None, timeout=6.0):
    """Get metadata via ffprobe."""
    if timeout == 0 or timeout == 0.0:
        timeout = None

    if logger is None:
        logger = logging.getLogger(__name__)

    if not ffprobe_exe or not os.path.exists(ffprobe_exe):
        logger.warning(f"FFprobe not found at: {ffprobe_exe}")
        return {}

    args = [
        ffprobe_exe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        path_to_file
    ]

    # Hide window on Windows
    creationflags = 0
    if os.name == 'nt':
        creationflags = 0x08000000 # subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(args, capture_output=True, text=True, check=True, creationflags=creationflags, timeout=timeout)
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

    if not oiiotool_exe or not os.path.exists(oiiotool_exe):
        logger.warning(f"OIIOTool not found at: {oiiotool_exe}")
        return {}

    # oiiotool doesn't have a direct JSON output for info in older versions
    # but we can parse the verbose output or use specific formatting if available.
    # For now, let's try a simple approach or look for --info:format json
    
    args = [
        oiiotool_exe,
        "--info:format=xml", "-v",
        path_to_file
    ]

    # Hide window on Windows
    creationflags = 0
    if os.name == 'nt':
        creationflags = 0x08000000 # subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(args, capture_output=True, text=True, check=True, creationflags=creationflags, timeout=timeout)
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
        return _ffprobe_metadata_conversion(video_stream)

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
    if "r_frame_rate" in metadata_stream or "framespersecond" in metadata_stream:
        rate_info = metadata_stream.get("r_frame_rate")
        if rate_info is None:
            rate_info = metadata_stream.get("framespersecond")

        if "/" in str(rate_info):
            try:
                num, den = str(rate_info).split("/")
                rate_info = float(num) / float(den)
            except: pass

        try:
            metadata_stream["framerate"] = float(str(rate_info))
        except Exception as e:
            logger.warning(f"Failed to evaluate '{rate_info}' to framerate: {e}")

    # Ensure width and height are integers
    for key in ["width", "height"]:
        if key in metadata_stream:
            try:
                metadata_stream[key] = int(metadata_stream[key])
            except: pass

    # Calculate start_from_tc if possible
    if "timecode" in metadata_stream and "framerate" in metadata_stream:
        tc = str(metadata_stream["timecode"])
        try:
            fps = float(metadata_stream["framerate"])
            # Handle various TC formats (HH:MM:SS:FF or HH:MM:SS;FF)
            parts = tc.replace(";", ":").split(":")
            if len(parts) == 4:
                h, m, s, f = map(int, parts)
                # Simple non-drop frame math
                start_frame = int((h * 3600 + m * 60 + s) * fps + f)
                metadata_stream["start_from_tc"] = start_frame
        except Exception:
            pass

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
