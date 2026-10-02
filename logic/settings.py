"""Preferences, presets and session state - one table, three files.

Files (all next to the application, never relative to the current directory):

  config.json                 Preferences, grouped by the Preferences-dialog tab
                              ({"format": 2, "General": {...}, "AYON": {...}, ...}).
  <presets>/users/<USER>.json The same, per user (when a Presets Folder is set).
  <presets>/<name>.json       A preset = a named, saved set of Preferences.
                              Presets never contain window/session state.
  session.json                Window and panel state (geometry, splitters,
                              filters, last folder, recent folders, AYON
                              selection, active preset). Saved often.
  install.json                Per-machine paths and credentials (unchanged).

In memory everything stays one flat dict (`self.config`) with the same key names
as before, so existing code keeps working; this module only decides which file a
key belongs to, which tab it is shown under, and what its default is.

Old flat files are read transparently (see `flatten`) and are rewritten in the
new layout on the next save.
"""
import json
import os
import tempfile

FORMAT_VERSION = 2

_THUMB_SCALE = r"scale=if(gte(iw\,ih)\,min({prefs_highres_thumb_size}\,iw)\,-4):if(lt(iw\,ih)\,min({prefs_highres_thumb_size}\,ih)\,-4)"
DEFAULT_CMD_STILLS = '{ffmpeg} -i "{filename}" -vf "' + _THUMB_SCALE + '" -y "{prefs_thumb_path}"'
DEFAULT_CMD_VIDEOS = ('{ffmpeg} -ss {metadata.thumbnail_time} -i "{filename}" -vframes 1 -vf "'
                      + _THUMB_SCALE + '" -y "{prefs_thumb_path}"')
DEFAULT_CMD_SEQUENCES = '{ffmpeg} -i "{metadata.seq_thumbnail_path}" -vf "' + _THUMB_SCALE + '" -y "{prefs_thumb_path}"'

# Preference sections = Preferences dialog tabs. key -> default
PREFERENCES = {
    "General": {
        "default_scan_folder": "",
        "age_source": "Modification Date",
        "detect_sequences": True,
        "version_collision": "fail",
        "create_ingest_report": True,
        "timezone_offset_a": "+00:00",
        "timezone_offset_b": "+00:00",
        "play_sounds": False,
    },
    "AYON": {
        "ayon_project": "",
        "product_name": "{label}",
        "product_name_camel": True,
        "duplicate_identity": "{ayon_path_val}{prod_name}{variant}{item.version}",
        "ayon_csv_ingest_folder": "/edit/csvingest",
        "ayon_csv_ingest_task": "csvingest",
        "ayon_csv_preset": "Default",
        "ayon_ignore_validators": True,
        "ayon_ingest_check": True,
        "get_ayon_thumbnails": True,
        "ayon_version_status": "Pending Review",
        "set_version_status_after_check": True,
        "set_product_status_after_check": True,
        "set_task_status_after_check": True,
        "set_neighbour_status_after_check": False,
        "neighbour_task_name": "comp",
        "neighbour_task_status": "Ready to start",
    },
    "AYON Items": {
        "ayon_item_task_type_priority": "Compositing Editing",
        "ayon_item_task_name_priority": "comp",
        "ayon_item_product_type_priority": "review render plate",
        "ayon_item_product_name_priority": "main",
        "ayon_item_product_version": "Max Version",
        "ayon_item_product_version_status": "",
        "ayon_item_repre_priority_extension": "mp4 mov png",
        "ayon_item_label": "{folder_name}/{task_name}/{product_name} v{version}",
        "item_info_ayon": "",
    },
    "Auto-Assign": {
        "version_parse": "File Name Only",
        "version_regex": r"([._]v|v)(\d+)",
        "version_repl": "",
        "folder_parse": "File Name Only",
        "folder_regex": r"^([^_]*_[^_]*)_.*$",
        "folder_repl": "",
        "folder_capitalization": "Keep Original",
        "task_parse": "File Name Only",
        "task_regex": r"^[^_]*_[^_]*_([^_]*).*$",
        "task_repl": "",
        "task_capitalization": "Keep Original",
        "fixed_task_name_enabled": False,
        "fixed_task_name": "",
        "variant_parse": "File Name Only",
        "variant_regex": r"^[^_]*_[^_]*_[^_]*_([^_]*).*$",
        "variant_repl": "",
        "variant_capitalization": "Keep Original",
        "sequence_parse": "File Name Only",
        "sequence_regex": r"^[^_]*_([^_]*)_[^_]*.*$",
        "sequence_repl": "",
        "sequence_capitalization": "Keep Original",
        "episode_parse": "File Name Only",
        "episode_regex": r"^[^_]*_([^_]*)_[^_]*.*$",
        "episode_repl": "",
        "episode_capitalization": "Keep Original",
        "auto_assign_multi_match": False,
        "auto_assign_fallback_task": False,
    },
    "CSV": {
        "csv_delimiter": ",",
        "csv_quotechar": '"',
        "csv_columns": "File Path={file_path}\nAYON Path={ayon_path}\nProduct Name={product_name}\nVariant={variant}\nVersion={version}",
    },
    "Conversions": {
        "run_thumb_after_scan": False,
        "run_review_after_scan": False,
        "skip_existing_thumbs": True,
        "skip_existing_reviews": True,
        "default_fps": 25.0,
        "use_fps_from_metadata": True,
        "seq_thumb_frame": "Middle",
        "thumb_size": 512,
        "thumb_location": "Relative to Source Folder",
        "thumb_location_path": "_thumbs",
        "thumb_suffix": "_thumbnail",
        "thumb_format": ".jpg",
        "thumb_quality": 80,
        "cmd_stills": DEFAULT_CMD_STILLS,
        "cmd_videos": DEFAULT_CMD_VIDEOS,
        "cmd_sequences": DEFAULT_CMD_SEQUENCES,
        "timeout_seconds": 6,
    },
    "Pairing": {
        # existing thumbnails / review movies linked to footage by name (logic/pairing.py)
        "pair_existing_media": True,
        "pair_name_mode": "same",          # "same" | "suffix" (allow a suffix after the same name)
        "pair_review_folder": "_review",   # other-folder reviews need this text in their path
        "pair_thumb_folder": "_thumb",     # other-folder thumbnails need this text in their path
        "pair_max_reviews": 1,
    },
    "Clipboard": {
        "clip_temp_root": "",
        "clip_folder_template": "IngestDesktop_{yy}{mm}{dd}",
        "clip_file_prefix": "clipboard",
        "clip_file_counter": 3,
    },
    "GUI": {
        "default_columns": 12,
        "default_text_size": 10,
        "default_thumb_size": 150,
        "label_allowed_chars": "^[a-zA-Z0-9_\\-\\.\\s]*$",
        "disable_inline_video": False,
        "edge_swipe_panels": True,
        "drawing_cache_location": "relative to source folder",
        "drawing_cache_path": "_drawcache",
        "item_info_generic": "",
    },
    "Presets": {
        "presets": {},
        "extensions": {},
        "item_info_stills": "",
        "item_info_sequences": "",
        "item_info_videos": "",
        "item_info_other": "",
        "stills_start_frame": 1001,
        "stills_end_frame": 1001,
        "stills_thumb_same": True,
        "video_start_from_tc": False,
        "video_start_frame": 1001,
    },
    "Grouping": {
        "group_by": "{folder_name}{task_name}{variant}{version}",
        "group_do_not_export_missing_repres": True,
        "group_definitions": [],
        "review_representations": ["mp4", "mov", "webm", "mxf"],
    },
}

# Window / panel state: saved to session.json, never into presets.
SESSION = {
    "active_preset": "",
    "geometry": None,
    "h_splitter": None,
    "v_splitter": None,
    "center_top_splitter": None,
    "last_source_folder": "",
    "recent_folders": [],
    "ayon_search_text": "",
    "ayon_search_column": 0,
    "ayon_selected_folder": "",
    "ayon_selected_task": "",
    "ayon_show_thumbs": True,
    "filter_age_enabled": False,
    "filter_age_value": 1,
    "filter_age_units": "days",
    "filter_files_only": False,
    "filter_flat": False,
    "filter_ignore_enabled": True,
    "filter_ignore_text": "",
    "filter_search_enabled": False,
    "filter_search_text": "",
    "filter_sequences": True,
    "filter_v_stack": False,
    "filter_toggles": {},
    "check_duplicates": True,
    "check_versions": True,
    "player_mode": "stop",
    "thumbnails_show_text": True,
    "thumbnails_show_frames": True,
    "show_reviews": True,
    "log_height": 200,          # log panel height (drag its top edge)
    "log_verbosity": "verbose",  # minimal | normal | verbose (log context menu)
    # "footage|review" pairs the user unpaired (a rescan does not pair them again)
    "unpaired_reviews": [],
    # "main|review" pairs made by hand ("Pair" / "Pair as main"); a rescan keeps them
    "manual_pairs": [],
}

# Keys that belong to install.json (per machine). Listed so they are never
# written into config.json / presets.
INSTALL_KEYS = {
    "presets_folder", "ayon_server_url", "traypublisher_path", "ffmpeg_path", "ffprobe_path",
    "oiiotool_path", "vfxtranscode", "ocio_config", "ayon_api_key", "ingest_log_folder",
    "per_project_logging", "ayon_thumbnails_cache", "ftrack_server", "ftrack_api_user",
    "ftrack_api_key", "deadline_job_name", "deadline_department", "deadline_pool",
    "deadline_secondary_pool", "deadline_group", "deadline_priority", "deadline_machine_limit",
    "deadline_concurrent_tasks", "sessions_folder", "load_last_session",
}

# Old key -> new key (values are moved on load)
RENAMED = {
    "high_res_size": "thumb_size",
    "thumbnail_size": "default_thumb_size",
    "ayon_project_name": "ayon_project",
    "last_ayon_project": "ayon_project",
}
# Keys that are no longer used anywhere
REMOVED = {"low_res_size", "thumbnails_per_row", "ayon_play_sound_on_finish", "format"}

KEY_SECTION = {k: sec for sec, keys in PREFERENCES.items() for k in keys}


def pref_keys():
    return set(KEY_SECTION)


def defaults():
    out = {}
    for keys in PREFERENCES.values():
        out.update(json.loads(json.dumps(keys)))   # deep copy
    out.update(json.loads(json.dumps(SESSION)))
    return out


def flatten(data):
    """Accept a sectioned (format 2) or an old flat dict; return a flat dict."""
    if not isinstance(data, dict):
        return {}
    if data.get("format") == FORMAT_VERSION:
        flat = {}
        for sec, val in data.items():
            if sec == "format":
                continue
            if isinstance(val, dict) and (sec in PREFERENCES or sec in ("Session", "Other")):
                flat.update(val)
            else:
                flat[sec] = val
        return migrate(flat)
    return migrate(dict(data))


def migrate(flat):
    """Rename/remove legacy keys. The first non-empty value of a renamed key wins."""
    for old, new in RENAMED.items():
        if old in flat:
            val = flat.pop(old)
            if val not in (None, "") and flat.get(new) in (None, ""):
                flat[new] = val
    for k in REMOVED:
        flat.pop(k, None)
    return flat


def sectioned_preferences(flat):
    """Preferences only (no session, no install keys), grouped by dialog tab."""
    out = {"format": FORMAT_VERSION}
    for sec, keys in PREFERENCES.items():
        out[sec] = {k: flat[k] for k in keys if k in flat}
    # keep unknown keys (e.g. added by a newer version) instead of dropping them
    other = {k: v for k, v in flat.items()
             if k not in KEY_SECTION and k not in SESSION and k not in INSTALL_KEYS
             and k not in RENAMED and k not in REMOVED and not k.startswith("_")}
    if other:
        out["Other"] = other
    return out


def session_state(flat):
    return {"format": FORMAT_VERSION, "Session": {k: flat[k] for k in SESSION if k in flat}}


def preferences_only(flat):
    """Flat dict of preference values (what a preset contains)."""
    return {k: v for k, v in flat.items()
            if k not in SESSION and k not in INSTALL_KEYS and k not in RENAMED
            and k not in REMOVED and not k.startswith("_")}


def with_aliases(flat):
    """Older code still reads these names; keep them in sync in memory only."""
    proj = flat.get("ayon_project", "")
    flat["ayon_project_name"] = proj
    flat["last_ayon_project"] = proj
    flat["high_res_size"] = flat.get("thumb_size", 512)
    flat["thumbnail_size"] = flat.get("default_thumb_size", 150)
    return flat


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        print(f"[Prefs] Cannot read {path}: {e}")
        return None


def write_json_atomic(path, data):
    """Write JSON via a temp file + rename, so a crash never leaves a half-written file."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
