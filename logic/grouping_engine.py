import logging

def compute_group_key(item, template=None):
    """Compute group key for an ImageItem based on template format string."""
    if not template:
        template = "{folder_name}{task_name}{variant}{version}"
        
    replacements = {
        "folder_name": item.metadata.get("folder_name", "") or "",
        "task_name": getattr(item, "task_name", "") or item.metadata.get("task_name", "") or "",
        "variant": getattr(item, "effective_variant", "") or getattr(item, "variant_user", "") or item.metadata.get("variant_parsed", "") or getattr(item, "variant", "") or "",
        "version": str(item.version) if getattr(item, "version", None) is not None else "",
        "episode": item.metadata.get("episode", "") or "",
        "sequence": item.metadata.get("sequence", "") or "",
        "label": getattr(item, "label", "") or "",
        "product_name": getattr(item, "product_name", "") or ""
    }
    
    key = template
    for var_name, val in replacements.items():
        key = key.replace("{" + var_name + "}", str(val))
    return key

def find_matching_group_def(group_items, group_defs):
    """Find the first matching enabled group definition for a list of items in a group."""
    if not group_defs or not group_items:
        return None

    for g_def in group_defs:
        if not g_def.get("enabled", True):
            continue

        task_types_str = g_def.get("task_types", "").strip()
        task_names_str = g_def.get("task_names", "").strip()

        type_match = True
        if task_types_str:
            allowed_types = {t.lower() for t in task_types_str.split()}
            type_match = any(
                (getattr(item, "task_type", "").lower() in allowed_types or 
                 getattr(item, "product_type", "").lower() in allowed_types)
                for item in group_items
            )

        name_match = True
        if task_names_str:
            allowed_names = {n.lower() for n in task_names_str.split()}
            name_match = any(
                getattr(item, "task_name", "").lower() in allowed_names
                for item in group_items
            )

        if type_match and name_match:
            return g_def

    return None

def validate_group_representations(group_items, group_def, config=None):
    """
    Validate whether all required representations are present in group_items according to group_def.
    Returns: (is_error, missing_repres)
    """
    if not group_def or not group_items:
        return False, []

    always_repres = [r.strip().lower() for r in group_def.get("always_repres", "").split() if r.strip()]
    always_or_convert = [r.strip().lower() for r in group_def.get("always_or_convert_repres", "").split() if r.strip()]

    if not always_repres and not always_or_convert:
        return False, []

    # Collect direct representations
    direct_repres = set()
    for item in group_items:
        repre = getattr(item, "representation", "") or ""
        if repre:
            direct_repres.add(repre.lower().lstrip("."))

    # Collect converted representations
    converted_repres = set(direct_repres)
    for item in group_items:
        if getattr(item, "convert_thumb", False) or (config and config.get("run_thumb_after_scan", False)):
            converted_repres.add("jpg")
            converted_repres.add("png")

        if getattr(item, "convert_review", False) or (config and config.get("run_review_after_scan", False)):
            rev_rep = (getattr(item, "review_representation", "") or "h264").lower().lstrip(".")
            converted_repres.add(rev_rep)
            converted_repres.add("mp4")
            converted_repres.add("mov")

    missing = []
    for req in always_repres:
        if req not in direct_repres:
            missing.append(req)

    for req in always_or_convert:
        if req not in converted_repres:
            missing.append(req)

    is_error = len(missing) > 0
    return is_error, missing

def get_item_priority(item, priority_list):
    """Get priority index for an item based on its representation in priority_list."""
    if not priority_list:
        return 999
    repre = (getattr(item, "representation", "") or "").lower().lstrip(".")
    if repre in priority_list:
        return priority_list.index(repre)
    return 999

def apply_group_inheritance(group_items, group_def):
    """Inherit non-empty column values from higher-priority items to lower-priority items in group."""
    if not group_def or not group_items:
        return

    priority_str = group_def.get("inheritance_repre_priority", "")
    inherit_cols_str = group_def.get("inherit_columns", "")

    priority_list = [p.strip().lower() for p in priority_str.split() if p.strip()]
    inherit_cols = [c.strip() for c in inherit_cols_str.split() if c.strip()]

    if not priority_list or not inherit_cols:
        return

    sorted_items = sorted(group_items, key=lambda it: get_item_priority(it, priority_list))

    for col in inherit_cols:
        # Find non-empty source value from highest priority item
        source_val = None
        for item in sorted_items:
            val = get_item_column_value(item, col)
            if val is not None and str(val).strip() != "":
                source_val = val
                break

        if source_val is not None:
            # Propagate to items that have empty/default values
            for item in sorted_items:
                cur_val = get_item_column_value(item, col)
                if cur_val is None or str(cur_val).strip() == "":
                    set_item_column_value(item, col, source_val)

def get_item_column_value(item, col_name):
    """Retrieve attribute or metadata value for a column name."""
    col_clean = col_name.lower().replace(" ", "_")
    if hasattr(item, col_clean):
        return getattr(item, col_clean)
    if hasattr(item, col_name):
        return getattr(item, col_name)
    if col_clean in item.metadata:
        return item.metadata[col_clean]
    if col_name in item.metadata:
        return item.metadata[col_name]
    return None

def set_item_column_value(item, col_name, val):
    """Set attribute or metadata value for a column name."""
    col_clean = col_name.lower().replace(" ", "_")
    if hasattr(item, col_clean):
        setattr(item, col_clean, val)
    elif hasattr(item, col_name):
        setattr(item, col_name, val)
    else:
        item.metadata[col_clean] = val

def pair_group_reviews(group_items, config=None):
    """
    Pair non-video items in a group with video items in the same group based on matching group keys.
    This replaces hardcoded file name filtering (e.g. _review) with dynamic grouping rules.
    Respects 'review_repre' in group definitions if specified.
    """
    import os
    if not group_items:
        return

    MEDIA_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".ogg", ".ogv", ".mxf")

    group_defs = config.get("group_definitions", []) if (config and isinstance(config, dict)) else []
    g_def = find_matching_group_def(group_items, group_defs) if group_defs else None

    target_review_repres = []
    if g_def:
        r_str = g_def.get("review_repre", "").strip()
        if r_str:
            target_review_repres = [r.lower().lstrip(".") for r in r_str.split()]

    video_items = []
    non_video_items = []

    for item in group_items:
        cat = getattr(item, "category", "") or ""
        fp = (getattr(item, "file_path", "") or "").lower()
        repre = (getattr(item, "representation", "") or "").lower().lstrip(".")
        
        is_video = (cat == "Video" or fp.endswith(MEDIA_EXTENSIONS) or repre in ("mp4", "mov", "webm", "mxf", "h264"))
        if target_review_repres and repre in target_review_repres:
            is_video = True

        if is_video:
            video_items.append(item)
        else:
            non_video_items.append(item)

    if video_items:
        # Select primary video item in the group
        primary_video = video_items[0]
        if target_review_repres:
            for tr in target_review_repres:
                found = False
                for v in video_items:
                    repre = (getattr(v, "representation", "") or "").lower().lstrip(".")
                    if repre == tr:
                        primary_video = v
                        found = True
                        break
                if found:
                    break
        else:
            for v in video_items:
                repre = (getattr(v, "representation", "") or "").lower().lstrip(".")
                if repre in ("mp4", "h264", "mov"):
                    primary_video = v
                    break

        video_path = primary_video.file_path.replace("\\", "/")

        for nv in non_video_items:
            nv.review_file_path = video_path
            nv.review_status = "done"

        for v in video_items:
            v.review_file_path = video_path
            v.review_status = "done"
            if (target_review_repres and repre in target_review_repres) or v == primary_video or getattr(v, "is_review_repre", False):
                v.is_review_repre = True
    else:
        for nv in non_video_items:
            rev_fp = getattr(nv, "review_file_path", None)
            if rev_fp and os.path.exists(rev_fp) and os.path.getsize(rev_fp) > 0:
                nv.review_status = "done"
            else:
                p_data = getattr(nv, "preset_data", {}) or {}
                if p_data.get("Convert Review", True):
                    source_file = (getattr(nv, "file_path", "") or "").replace("\\", "/")
                    if source_file:
                        base_dir = os.path.dirname(source_file)
                        r_path = p_data.get("Review Path", "_reviews")
                        r_suf = p_data.get("Review Suffix", "_review")
                        r_fmt = p_data.get("Review Format", ".mp4")
                        filename = os.path.basename(source_file)
                        name_no_ext, _ = os.path.splitext(filename)
                        if getattr(nv, "is_sequence", False):
                            from logic.image_model import strip_sequence_counter
                            name_no_ext = strip_sequence_counter(name_no_ext)
                        exp_path = os.path.join(base_dir, r_path, f"{name_no_ext}{r_suf}{r_fmt}").replace("\\", "/")
                        if os.path.exists(exp_path) and os.path.getsize(exp_path) > 0:
                            nv.review_file_path = exp_path
                            nv.review_status = "done"
                        else:
                            nv.review_status = "waiting"
                    else:
                        nv.review_status = "waiting"
                else:
                    nv.review_status = "do not convert"

def apply_thumbnail_source_inheritance(group_items, g_def):
    """
    If g_def specifies 'thumb_source_repre', locate the source item matching the representation
    and share its thumbnail image / thumbnail path to other items in the group.
    """
    if not g_def or not group_items:
        return

    ts_str = g_def.get("thumb_source_repre", "").strip()
    if not ts_str:
        return

    target_repres = [r.lower().lstrip(".") for r in ts_str.split()]
    source_item = None
    for tr in target_repres:
        for item in group_items:
            repre = (getattr(item, "representation", "") or "").lower().lstrip(".")
            if repre == tr:
                source_item = item
                break
        if source_item:
            break

    if source_item and getattr(source_item, "thumbnail_image", None):
        thumb_img = source_item.thumbnail_image
        thumb_path = getattr(source_item, "conversion_thumb_path", None)
        for item in group_items:
            if item != source_item and not getattr(item, "thumbnail_image", None):
                item.thumbnail_image = thumb_img
                if thumb_path:
                    item.conversion_thumb_path = thumb_path


