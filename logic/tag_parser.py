"""Parse version and tags (folder_name, task_name, variant_parsed, sequence,
episode) from an item's file name or path, using the Auto-Assign preferences.

Pure Python (no Qt) so it can run inside the scanner thread *before* presets
and grouping are evaluated, and be unit-tested on its own.
"""
import os
import re
import logging

from utils import apply_capitalization


def get_parse_target(item, parse_mode, scan_folder=""):
    """Helper to compute target string for regex matching according to parse_mode."""
    file_path = getattr(item, "file_path", "") or ""
    file_path_norm = file_path.replace("\\", "/")
    dir_norm = os.path.dirname(file_path_norm)
    filename = os.path.basename(file_path_norm)

    if parse_mode == "Path Only":
        return dir_norm
    elif parse_mode == "Full Path":
        return file_path_norm
    elif parse_mode and parse_mode.startswith("Folder +"):
        try:
            n = int(parse_mode.replace("Folder +", "").strip())
        except ValueError:
            n = 1
        if scan_folder:
            scan_norm = scan_folder.replace("\\", "/").rstrip("/")
            if dir_norm.lower().startswith(scan_norm.lower()):
                rel = dir_norm[len(scan_norm):].strip("/")
                parts = [p for p in rel.split("/") if p and p != "."]
                if 0 <= (n - 1) < len(parts):
                    return parts[n - 1]
        return ""
    elif parse_mode and parse_mode.startswith("Folder -"):
        try:
            n = int(parse_mode.replace("Folder -", "").strip())
        except ValueError:
            n = 1
        parts = [p for p in dir_norm.split("/") if p]
        if 0 <= (n - 1) < len(parts):
            return parts[-n]
        return ""
    else:
        # Default: "File Name Only"
        return filename


def parse_item_tags(item, config, scan_folder=""):
    """Parse filename or path using regexes and repl expressions according to parse settings and store in item.metadata."""

    def _apply_repl(match, repl_str, default_val):
        """Helper to process third step: Repl (regex expand or lambda evaluation with support for arbitrary text & \\1, \\2... \\n groups)."""
        if not repl_str or not repl_str.strip():
            return default_val
        repl_clean = repl_str.strip()
        if repl_clean.startswith("lambda"):
            try:
                fn = eval(repl_clean, {"re": re, "os": os, "str": str, "int": int, "float": float, "len": len, "abs": abs, "min": min, "max": max})
                return str(fn(match))
            except Exception as e:
                logging.error(f"Error evaluating lambda repl '{repl_clean}': {e}")
                return default_val
        else:
            try:
                return match.expand(repl_clean)
            except Exception:
                pass

            try:
                res = repl_clean

                def replace_g(m):
                    k = m.group(1)
                    if k.isdigit():
                        idx = int(k)
                        return str(match.group(idx)) if 0 <= idx <= len(match.groups()) else m.group(0)
                    return str(match.group(k))
                res = re.sub(r"\\g<([^>]+)>", replace_g, res)

                num_groups = len(match.groups())
                for g_idx in range(num_groups, 0, -1):
                    target = f"\\{g_idx}"
                    if target in res:
                        g_val = match.group(g_idx)
                        if g_val is not None:
                            res = res.replace(target, str(g_val))

                if "\\0" in res:
                    res = res.replace("\\0", str(match.group(0) or ""))

                return res
            except Exception as e:
                logging.error(f"Error expanding regex repl '{repl_clean}': {e}")
                return default_val

    # Version
    # 1. First: Parse dropdown target
    v_parse = config.get("version_parse", "File Name Only")
    v_target = get_parse_target(item, v_parse, scan_folder)
    v_regex = config.get("version_regex", r"([._]v|v)(\d+)")
    v_repl = config.get("version_repl", "")

    if v_target:
        v_pattern = v_regex if v_regex else r"(\d+)"
        try:
            # 2. Second: Regex
            v_match = re.search(v_pattern, v_target)
            if v_match:
                # 3. Third: Repl
                if v_repl and v_repl.strip():
                    ver_str = _apply_repl(v_match, v_repl, "")
                else:
                    groups = v_match.groups()
                    if len(groups) >= 2:
                        ver_str = groups[1]
                    elif len(groups) == 1:
                        ver_str = groups[0]
                    else:
                        ver_str = v_match.group(0)

                digits_match = re.search(r"\d+", ver_str)
                if digits_match:
                    item.version = int(digits_match.group(0))
                elif ver_str.isdigit():
                    item.version = int(ver_str)
        except (ValueError, IndexError, re.error, Exception) as e:
            logging.error(f"Error parsing version for {item.filename}: {e}")

    # Tags (folder_name, task_name, variant_parsed, sequence, episode)
    tag_config = {
        "folder_name": (config.get("folder_parse", "File Name Only"), config.get("folder_regex"), config.get("folder_repl", ""), config.get("folder_capitalization", "Keep Original")),
        "task_name": (config.get("task_parse", "File Name Only"), config.get("task_regex"), config.get("task_repl", ""), config.get("task_capitalization", "Keep Original")),
        "variant_parsed": (config.get("variant_parse", "File Name Only"), config.get("variant_regex", r"^[^_]*_[^_]*_[^_]*_([^_]*).*$"), config.get("variant_repl", ""), config.get("variant_capitalization", "Keep Original")),
        "sequence": (config.get("sequence_parse", "File Name Only"), config.get("sequence_regex"), config.get("sequence_repl", ""), config.get("sequence_capitalization", "Keep Original")),
        "episode": (config.get("episode_parse", "File Name Only"), config.get("episode_regex"), config.get("episode_repl", ""), config.get("episode_capitalization", "Keep Original"))
    }

    for tag, (parse_mode, pattern, repl, cap_style) in tag_config.items():
        if tag == "task_name" and config.get("fixed_task_name_enabled", False):
            val = config.get("fixed_task_name", "")
            val = apply_capitalization(val, cap_style)
            item.metadata["task_name"] = val
            logging.info(f"Using fixed task_name={val} for {item.filename}")
            continue

        # 1. First: Parse dropdown target
        target_str = get_parse_target(item, parse_mode, scan_folder)
        if not target_str:
            continue

        # 2. Second: Regex
        pattern_to_use = pattern if pattern else (r"(.*)" if parse_mode != "File Name Only" or repl else None)
        if not pattern_to_use:
            continue

        try:
            match = re.search(pattern_to_use, target_str)
        except re.error as e:
            logging.error(f"Regex error for {tag}: {e}")
            match = None

        if match:
            default_val = match.group(1) if match.groups() else match.group(0)
            # 3. Third: Repl
            val = _apply_repl(match, repl, default_val)
        elif parse_mode and (parse_mode.startswith("Folder +") or parse_mode.startswith("Folder -")):
            val = target_str
        else:
            val = None

        if val is not None:
            # 4. Fourth: Capitalization
            val = apply_capitalization(val, cap_style)
            item.metadata[tag] = val
            logging.info(f"Parsed tag {tag}={val} from {target_str} (mode: {parse_mode})")
        else:
            logging.debug(f"Regex {tag} did not match {target_str} with pattern {pattern}")

    # Remember what came from the file name so clearing an AYON assignment can restore it
    item.parsed_tags = {k: item.metadata[k] for k in ("folder_name", "task_name", "variant_parsed", "sequence", "episode")
                        if k in item.metadata}
