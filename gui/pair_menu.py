"""'Unpair' context-menu entries shared by the canvas, file panel and spreadsheet.

Pairs are (main item, review item), see ImageItem.pair_review (logic/image_model.py).
"""
import os

from PySide6.QtGui import QAction


def pairs_of(items):
    """Every (main, review) pair touching the given items, in a stable order, no duplicates."""
    out, seen = [], set()
    for it in items or []:
        if it is None:
            continue
        cand = []
        main = getattr(it, "pair_main", None)
        if main is not None:
            cand.append((main, it))
        cand += [(it, r) for r in (getattr(it, "paired_reviews", None) or [])]
        for pair in cand:
            key = (id(pair[0]), id(pair[1]))
            if key not in seen:
                seen.add(key)
                out.append(pair)
    return out


def add_unpair_actions(menu, items, on_unpair, parent=None):
    """Add the unpair entries for the selected items. on_unpair(list_of_pairs) does the work.

    * Selection within one pair (a main file and/or its reviews): an "Unpair"
      submenu listing that pair's reviews by file name, plus "All" when there are
      several.
    * Selection spanning several pairs: one "Unpair" action that unpairs all of them.
    Returns True when something was added."""
    items = [it for it in (items or []) if it is not None]
    pairs = pairs_of(items)
    if not pairs:
        return False
    parent = parent or menu
    mains = []
    for main, _review in pairs:
        if all(m is not main for m in mains):
            mains.append(main)
    if len(mains) == 1:
        main = mains[0]
        group = [(main, r) for r in getattr(main, "paired_reviews", [])]
        sub = menu.addMenu("Unpair")
        for m, review in group:
            act = QAction(os.path.basename(review.file_path), parent)
            act.triggered.connect(lambda checked=False, p=(m, review): on_unpair([p]))
            sub.addAction(act)
        if len(group) > 1:
            sub.addSeparator()
            act_all = QAction("All", parent)
            act_all.triggered.connect(lambda checked=False, ps=list(group): on_unpair(ps))
            sub.addAction(act_all)
    else:
        act = QAction("Unpair", parent)
        act.triggered.connect(lambda checked=False, ps=list(pairs): on_unpair(ps))
        menu.addAction(act)
    return True


def repair_candidates(items, all_items, unpaired_keys):
    """(main, review) pairs the user unpaired earlier that touch the selected items
    and can be paired again (both still loaded, neither paired elsewhere as a review)."""
    from logic.pairing import unpair_key, footage_id
    keys = [k for k in (unpaired_keys or []) if isinstance(k, str) and "|" in k]
    if not keys or not items:
        return []
    by_path, by_footage = {}, {}
    for it in all_items or []:
        if getattr(it, "file_path", None):
            by_path.setdefault(unpair_key(it.file_path, it.file_path).split("|")[0], it)
            by_footage.setdefault(footage_id(it.file_path), it)
    selected = {id(it) for it in items}
    out = []
    for k in keys:
        fp, rp = k.split("|", 1)
        main, review = by_path.get(fp) or by_footage.get(footage_id(fp)), by_path.get(rp)
        if main is None or review is None or main is review:
            continue
        if id(main) not in selected and id(review) not in selected:
            continue
        if getattr(main, "pair_main", None) is not None or getattr(review, "pair_main", None) is not None:
            continue
        if review in (getattr(main, "paired_reviews", None) or []):
            continue
        out.append((main, review))
    return out


def add_pair_actions(menu, items, all_items, unpaired_keys, on_pair, parent=None):
    """"Pair" for items that were unpaired before (remembered): a submenu listing the
    reviews when the selection is within one main file, one "Pair" action otherwise."""
    pairs = repair_candidates([it for it in (items or []) if it is not None], all_items, unpaired_keys)
    if not pairs:
        return False
    parent = parent or menu
    mains = []
    for main, _r in pairs:
        if all(m is not main for m in mains):
            mains.append(main)
    if len(mains) == 1:
        sub = menu.addMenu("Pair")
        for m, review in pairs:
            act = QAction(os.path.basename(review.file_path), parent)
            act.triggered.connect(lambda checked=False, p=(m, review): on_pair([p]))
            sub.addAction(act)
        if len(pairs) > 1:
            sub.addSeparator()
            act_all = QAction("All", parent)
            act_all.triggered.connect(lambda checked=False, ps=list(pairs): on_pair(ps))
            sub.addAction(act_all)
    else:
        act = QAction("Pair", parent)
        act.triggered.connect(lambda checked=False, ps=list(pairs): on_pair(ps))
        menu.addAction(act)
    return True


def unpaired_keys_of(model):
    """Remembered unpairs, provided by the main window (model.get_unpaired)."""
    model = getattr(model, "source_model", None) or model
    getter = getattr(model, "get_unpaired", None)
    try:
        return list(getter() or []) if callable(getter) else []
    except Exception:
        return []


def add_pairing_actions(menu, items, model, on_unpair, on_pair, parent=None):
    """Unpair / Pair entries for the selection. Returns True when something was added."""
    src = getattr(model, "source_model", None) or model
    all_items = getattr(src, "all_items", None) or getattr(src, "items", None) or []
    a = add_unpair_actions(menu, items, on_unpair, parent)
    b = add_pair_actions(menu, items, all_items, unpaired_keys_of(model), on_pair, parent)
    return a or b


def add_pair_as_main_actions(menu, items, on_pair, parent=None, limit=30):
    """"Pair as main" submenu (spreadsheet): lists the selected rows; the chosen one
    becomes the main file and every other selected row becomes its paired review.
    on_pair(list_of_pairs). Returns True when something was added."""
    items = [it for it in (items or []) if it is not None and not getattr(it, "is_ayon_item", False)]
    if len(items) < 2 or len(items) > limit:
        return False
    parent = parent or menu
    sub = menu.addMenu("Pair as main")
    for main in items:
        others = [it for it in items if it is not main]
        act = QAction(os.path.basename(main.file_path), parent)
        act.setToolTip(f"{os.path.basename(main.file_path)} becomes the main file of the other {len(others)} selected")
        act.triggered.connect(lambda checked=False, m=main, o=others: on_pair([(m, r) for r in o]))
        sub.addAction(act)
    return True
