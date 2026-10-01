import os

def _match(items, key, prio):
    """Items whose `key` equals `prio` (case-insensitive); if none, those containing it.
    Exact matches win, so "comp" picks "comp" before "precomp". None values are safe."""
    vals = [((it.get(key) or "") if isinstance(it, dict) else "").lower() for it in items]
    exact = [it for it, v in zip(items, vals) if v == prio]
    if exact:
        return exact
    return [it for it, v in zip(items, vals) if prio in v]


def autopick_task(tasks, task_type_priority_str="", task_name_priority_str=""):
    """
    Autopicks a task from a list of AYON task dicts.
    task_type_priority_str: space-separated priority list for task types.
    task_name_priority_str: space-separated priority list for task names.
    """
    if not tasks:
        return None

    type_prios = [t.strip().lower() for t in task_type_priority_str.split() if t.strip()]
    name_prios = [n.strip().lower() for n in task_name_priority_str.split() if n.strip()]

    candidates = list(tasks)

    # 1. Filter by Task Type Priority
    if type_prios:
        for t_prio in type_prios:
            matched = _match(candidates, "type", t_prio)
            if matched:
                candidates = matched
                break

    # 2. Filter by Task Name Priority
    if name_prios:
        for n_prio in name_prios:
            matched = _match(candidates, "name", n_prio)
            if matched:
                return matched[0]

    return candidates[0] if candidates else tasks[0]


def autopick_product(products, product_type_priority_str="", product_name_priority_str=""):
    """
    Autopicks a product from a list of AYON product dicts.
    Matches are case-insensitive substring matches.
    """
    if not products:
        return None

    type_prios = [t.strip().lower() for t in product_type_priority_str.split() if t.strip()]
    name_prios = [n.strip().lower() for n in product_name_priority_str.split() if n.strip()]

    candidates = list(products)

    # 1. Filter by Product Type Priority
    if type_prios:
        for t_prio in type_prios:
            matched = _match(candidates, "type", t_prio)
            if matched:
                candidates = matched
                break

    # 2. Filter by Product Name Priority
    if name_prios:
        for n_prio in name_prios:
            matched = _match(candidates, "name", n_prio)
            if matched:
                return matched[0]

    return candidates[0] if candidates else products[0]


def autopick_version(versions, version_mode="Max Version", version_status_filter=""):
    """
    Autopicks a version dict from a list of version dicts (each having 'version' and 'status'/'version_status').
    version_mode: "Max Version", "Min Version", "by Status or Max", "by Status Only"
    """
    if not versions:
        return None

    def get_ver_num(v):
        try:
            return int(v.get("version", 0))
        except (ValueError, TypeError):
            return 0

    def get_status(v):
        return (v.get("status") or v.get("version_status") or "").strip().lower()

    target_status = (version_status_filter or "").strip().lower()

    if version_mode == "Min Version":
        return min(versions, key=get_ver_num)
    elif version_mode == "by Status Only":
        matched = [v for v in versions if target_status and get_status(v) == target_status]
        return matched[0] if matched else None
    elif version_mode == "by Status or Max":
        matched = [v for v in versions if target_status and get_status(v) == target_status]
        if matched:
            return max(matched, key=get_ver_num)
        return max(versions, key=get_ver_num)
    else:  # "Max Version" (default)
        return max(versions, key=get_ver_num)


def autopick_representation(repres, extension_priority_str=""):
    """
    Autopicks a representation dict from a list of representation dicts based on file extension priority.
    """
    if not repres:
        return None

    ext_prios = [e.strip().lower().lstrip(".") for e in extension_priority_str.split() if e.strip()]
    if not ext_prios:
        return repres[0]

    for ext in ext_prios:
        for r in repres:
            path = r.get("attrib", {}).get("path", "")
            r_name = (r.get("name") or "").lower()
            file_ext = os.path.splitext(path)[1].lower().lstrip(".") if path else ""

            if file_ext == ext or r_name == ext:
                return r

    return repres[0]
