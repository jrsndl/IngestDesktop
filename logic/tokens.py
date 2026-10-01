"""Token engine: turns templates such as "{product_type}{variant}" into text.

This is the ONLY place where token values are defined. Everything that fills
templates (Qt model columns, tooltips, CSV export, conversion commands, group
keys, duplicate identity) goes through `expand()`.

Order of operations (documented so it can be relied on)
------------------------------------------------------
1. A template is scanned once for `{name}` tokens. Token names are case- and
   space-insensitive: `{Folder Name}` == `{folder_name}` == `{FOLDER_NAME}`.
2. Each token is resolved lazily (only tokens that appear are computed) and
   cached for the duration of one expand() call.
3. Values of *template tokens* (variant, representation, product_name) can
   themselves contain tokens - e.g. a preset Variant of "{label}". Those are
   expanded recursively before being inserted. A token that refers to itself
   (directly or indirectly) resolves to "" instead of recursing forever.
4. Context values follow a fixed precedence:
      AYON assignment  >  user edits (Variant User / Version User)
                       >  values parsed from the file name  >  preset values
5. CamelCase is applied only when asked for (product name and variant). It
   capitalises the first letter of every token value that is not at the very
   start of the template. Commands, paths, tooltips and CSV cells are never
   camel-cased.
6. `{metadata.KEY}` reads item.metadata[KEY]; unknown tokens are left as-is.
7. Tool tokens ({ffmpeg}, {ffprobe}, {oiiotool}, {vfxtranscode}) are wrapped in
   double quotes when the path contains spaces and the template does not quote
   them already, so "C:/Program Files/..." works in commands.
"""
import os
import re

TOKEN_RE = re.compile(r"\{([^{}\n]+)\}")

# Alternative spellings that existed in older templates -> canonical name
ALIASES = {
    "repre": "representation",
    "prod_name": "product_name",
    "item.version": "version",
    "ayon_path_val": "ayon_path",
}

# Tokens whose value may itself be a template
TEMPLATE_TOKENS = {"variant", "representation", "product_name"}

# Tokens that hold executable paths (auto-quoted in commands when needed)
TOOL_TOKENS = {"ffmpeg", "ffprobe", "oiiotool", "vfxtranscode"}

_SEQ_COUNTER_RE = re.compile(r"(\d+)$")


def normalize(name):
    n = name.strip().lower().replace(" ", "_")
    return ALIASES.get(n, n)


def _s(val):
    return "" if val is None else str(val)


def _camel(val):
    return val[0].upper() + val[1:] if val else val


class _Settings:
    """Defaults used when expand() gets no settings object (e.g. in tests)."""
    product_name_template = "{label}"
    product_name_camel = True
    default_fps = 25.0
    use_fps_from_metadata = True
    stills_thumb_same = True
    high_res_size = 512
    ffmpeg_path = "ffmpeg.exe"
    ffprobe_path = "ffprobe.exe"
    oiiotool_path = "oiiotool.exe"
    vfxtranscode = ""
    ocio_config = ""
    app_dir = ""

    def prefs_thumb_path(self, item):
        return ""

    def prefs_review_path(self, item):
        return ""


class _Resolver:
    def __init__(self, item, settings):
        self.item = item
        self.s = settings or _Settings()
        self.cache = {}
        self.stack = set()

    # -- helpers ---------------------------------------------------------
    def _get(self, attr, default=None):
        return getattr(self.s, attr, getattr(_Settings, attr, default))

    def _meta(self, key):
        md = self.item.metadata or {}
        return md.get(key)

    def _ayon(self, key):
        """Value coming from the AYON assignment (only while assigned)."""
        it = self.item
        if not getattr(it, "ayon_path", ""):
            return None
        ctx = getattr(it, "ayon_context", None) or {}
        return ctx.get(key) or None

    def _ayon_parts(self):
        return [p for p in (getattr(self.item, "ayon_path", "") or "").split("/") if p]

    def _preset(self):
        return getattr(self.item, "preset_data", None) or {}

    # -- public ----------------------------------------------------------
    def value(self, name):
        if name in self.cache:
            return self.cache[name]
        if name in self.stack:          # self-reference -> empty, never recurse forever
            return ""
        self.stack.add(name)
        try:
            val = self._compute(name)
        finally:
            self.stack.discard(name)
        if val is not None:
            val = _s(val)
        self.cache[name] = val
        return val

    def expand_nested(self, template, camel):
        return _expand_with(self, template, camel)

    # -- token values ----------------------------------------------------
    def _compute(self, name):
        it = self.item
        if name.startswith("metadata."):
            key = name[len("metadata."):]
            md = it.metadata or {}
            v = md.get(key)
            if v is None:
                v = md.get(key.lower())
            return None if v is None else v

        fn = getattr(self, "t_" + name.replace(".", "_"), None)
        if fn is None:
            return None
        return fn()

    # AYON context ---------------------------------------------------------
    def t_ayon_path(self):
        return getattr(self.item, "ayon_path", "") or ""

    def t_ayon_folder_path(self):
        parts = (getattr(self.item, "ayon_path", "") or "").split("/")
        return "/".join(parts[:-1])

    def t_ayon_task_name(self):
        return getattr(self.item, "ayon_task_name", "") or ""

    def t_ayon_task_type(self):
        return getattr(self.item, "ayon_task_type", "") or ""

    def t_ayon_task_assignee(self):
        return getattr(self.item, "ayon_task_assignee", "") or ""

    def t_folder_path(self):
        return (self._ayon("folder_path") or self._meta("folder_path")
                or self.t_ayon_folder_path() or self.t_ayon_path())

    def t_folder_name(self):
        v = self._ayon("folder_name") or self._meta("folder_name")
        if v:
            return v
        parts = self._ayon_parts()
        return parts[-2] if len(parts) > 1 else ""

    def t_task_name(self):
        v = (getattr(self.item, "ayon_task_name", "") or self._ayon("task_name")
             or getattr(self.item, "task_name", "") or self._meta("task_name"))
        if v:
            return v
        parts = self._ayon_parts()
        return parts[-1] if parts else ""

    def t_task_type(self):
        return (getattr(self.item, "ayon_task_type", "") or self._ayon("task_type")
                or self._meta("task_type") or "")

    def _ctx_meta(self, key):
        return self._ayon(key) or self._meta(key) or ""

    def t_folder_description(self): return self._ctx_meta("folder_description")
    def t_folder_status(self): return self._ctx_meta("folder_status")
    def t_folder_type(self): return self._ctx_meta("folder_type")
    def t_task_description(self): return self._ctx_meta("task_description")
    def t_task_status(self): return self._ctx_meta("task_status")
    def t_sequence(self): return self._meta("sequence") or ""
    def t_episode(self): return self._meta("episode") or ""
    def t_variant_parsed(self): return self._meta("variant_parsed") or ""

    # Product / version ----------------------------------------------------
    def t_version(self):
        return getattr(self.item, "effective_version", getattr(self.item, "version", ""))

    def t_version_user(self):
        return getattr(self.item, "version_user", "") or ""

    def t_variant_user(self):
        return getattr(self.item, "variant_user", "") or ""

    def t_variant(self):
        tmpl = getattr(self.item, "effective_variant", None)
        if tmpl is None:
            tmpl = getattr(self.item, "variant", "") or ""
        return self.expand_nested(tmpl, camel=bool(getattr(self.item, "camel_case", True)))

    def t_product_type(self):
        return getattr(self.item, "product_type", None) or self._meta("product_type") or ""

    def t_product_name(self):
        # AYON items carry their real product name
        v = self._meta("product_name")
        if v:
            return v
        tmpl = self._get("product_name_template") or "{label}"
        return self.expand_nested(tmpl, camel=bool(self._get("product_name_camel")))

    def t_product_version(self):
        v = self._meta("product_version")
        if v:
            return v
        ev = self.t_version()
        return f"v{ev:03d}" if isinstance(ev, int) else _s(ev)

    def t_product_status(self): return self._meta("product_status") or ""
    def t_product_source(self): return self._meta("product_source") or ""

    def t_representation(self):
        tmpl = (getattr(self.item, "representation", None) or self._meta("representation")
                or self._preset().get("Representation") or "{extension}")
        return self.expand_nested(tmpl, camel=False)

    # File ---------------------------------------------------------------
    def t_label(self):
        return getattr(self.item, "label", "") or ""

    def _hashed(self, printf=False):
        fp = (getattr(self.item, "file_path", "") or "").replace("\\", "/")
        if not getattr(self.item, "is_sequence", False):
            return fp
        base, ext = os.path.splitext(fp)
        m = _SEQ_COUNTER_RE.search(base)
        if not m:
            return fp
        digits = m.group(1)
        pad = f"%0{len(digits)}d" if printf else "#" * len(digits)
        return base[:m.start()] + pad + ext

    def t_filename(self): return self._hashed(False)
    def t_filename_printf(self): return self._hashed(True)

    def t_file_path(self):
        return (getattr(self.item, "file_path", "") or "").replace("\\", "/")

    def t_file_name(self):
        return os.path.splitext(os.path.basename(getattr(self.item, "file_path", "") or ""))[0]

    def t_extension(self):
        return os.path.splitext(getattr(self.item, "file_path", "") or "")[1].replace(".", "").lower()

    def t_parent_folder(self):
        return os.path.basename(os.path.dirname(getattr(self.item, "file_path", "") or ""))

    def t_frame_start(self):
        v = getattr(self.item, "frame_start", None)
        return "" if v is None else v

    def t_frame_end(self):
        v = getattr(self.item, "frame_end", None)
        return "" if v is None else v

    def t_comment(self): return getattr(self.item, "comment", "") or ""

    def t_is_duplicate(self):
        return "True" if getattr(self.item, "is_duplicate", False) else "False"

    def t_version_collision(self):
        return _s(getattr(self.item, "version_collision", "None"))

    def t_ingest_status(self):
        return getattr(self.item, "ingest_status", "unknown")

    # Preset values ------------------------------------------------------
    def t_head(self): return _s(self._preset().get("Handle Start", "0"))
    def t_tail(self): return _s(self._preset().get("Handle End", "0"))
    def t_slate_exists(self): return "True" if self._preset().get("Slate Exists") else "False"
    def t_repre_color(self): return self._preset().get("Colorspace", "") or ""
    def t_repre_tags(self): return self._preset().get("Tags", "") or ""
    def t_review_repre(self): return self._preset().get("Review Representation", "h264")
    def t_review_colorspace(self): return self._preset().get("Review Colorspace", "Output - sRGB")
    def t_review_tags(self): return self._preset().get("Review Tags", "passing;ftrackreview;webreview")

    def _fps(self):
        p = self._preset()
        if p.get("FPS Override", False):
            try:
                return float(p.get("FPS"))
            except (TypeError, ValueError):
                pass
        elif self._get("use_fps_from_metadata", True) and p.get("FPS From Metadata", True):
            try:
                v = self._meta("framerate")
                if v is not None:
                    return float(v)
            except (TypeError, ValueError):
                pass
        return float(self._get("default_fps", 25.0) or 25.0)

    def t_fps(self): return str(self._fps())
    def t_fps_int(self): return str(int(round(self._fps())))

    # Paths / settings ---------------------------------------------------
    def t_thumb_path(self):
        if getattr(self.item, "category", "") == "Still" and self._get("stills_thumb_same", True):
            return self.t_filename()
        return ""

    def t_prefs_highres_thumb_size(self): return str(self._get("high_res_size", 512))
    def t_prefs_thumb_path(self): return self.s.prefs_thumb_path(self.item) if hasattr(self.s, "prefs_thumb_path") else ""
    def t_prefs_review_path(self): return self.s.prefs_review_path(self.item) if hasattr(self.s, "prefs_review_path") else ""

    def _abs(self, p):
        return os.path.abspath(p).replace("\\", "/") if p else ""

    def t_ffmpeg(self): return self._get("ffmpeg_path", "ffmpeg.exe") or ""
    def t_ffprobe(self): return self._get("ffprobe_path", "ffprobe.exe") or ""
    def t_oiiotool(self): return self._get("oiiotool_path", "oiiotool.exe") or ""
    def t_vfxtranscode(self): return self._abs(self._get("vfxtranscode", ""))
    def t_ocio(self): return self._abs(self._get("ocio_config", ""))
    def t_ingestdesktop(self): return (self._get("app_dir", "") or "").replace("\\", "/")


def _expand_with(resolver, template, camel):
    if not template:
        return ""

    def repl(m):
        raw = m.group(1)
        name = normalize(raw)
        val = resolver.value(name)
        if val is None:
            return m.group(0)       # unknown token: keep it visible
        if name in TOOL_TOKENS and " " in val:
            before = template[m.start() - 1] if m.start() > 0 else ""
            after = template[m.end()] if m.end() < len(template) else ""
            if before not in ('"', "'") and after not in ('"', "'"):
                val = f'"{val}"'
        if camel and m.start() > 0:
            val = _camel(val)
        return val

    return TOKEN_RE.sub(repl, template)


def expand(template, item, settings=None, camel=False):
    """Expand all tokens in `template` for `item`.

    settings: any object providing the attributes of `_Settings` (the Qt model does).
    camel:    CamelCase non-leading token values (product names / variants only).
    """
    return _expand_with(_Resolver(item, settings), template, camel)


def all_values(item, settings=None, names=None):
    """Return {"{name}": value} for every known token (used by the Key/Value column)."""
    r = _Resolver(item, settings)
    names = names or sorted(n[2:] for n in dir(_Resolver) if n.startswith("t_"))
    out = {}
    for n in names:
        v = r.value(n)
        if v is not None:
            out["{" + n + "}"] = v
    return out


def known_tokens():
    return sorted(n[2:] for n in dir(_Resolver) if n.startswith("t_"))
