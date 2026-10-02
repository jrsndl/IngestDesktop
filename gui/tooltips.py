"""Tooltips for every button, toggle and input of the interface.

All texts live here (one place to edit, one place to translate). They are
applied automatically: `install_all()` wraps the __init__ of each GUI class
listed in TIPS, so every instance - also the ones created later, e.g. presets
and group definitions in Preferences - gets its tooltips right after it is
built. A text from this table replaces a tooltip the widget set itself.

Widgets that are local variables (not `self.xxx` attributes) get their
tooltips inline where they are created, using `tip()` so the text is
formatted the same way.

Form labels: the text label in front of a field ("Thumbnail Path:") gets the
field's tooltip too, so hovering the label works as well.

Tooltip delay: main.py installs `TooltipDelayStyle` - tooltips appear after
TOOLTIP_DELAY_MS so they never get in the way of normal work. Once one tooltip
is shown, moving to the next control shows its tooltip immediately (Qt default).
"""
import html

from PySide6.QtWidgets import (QWidget, QLabel, QFormLayout, QGridLayout, QBoxLayout,
                               QProxyStyle, QStyle, QTabWidget)

TOOLTIP_DELAY_MS = 2000


class TooltipDelayStyle(QProxyStyle):
    """App style that only changes how long the mouse must rest before a tooltip shows."""

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.SH_ToolTip_WakeUpDelay:
            return TOOLTIP_DELAY_MS
        return super().styleHint(hint, option, widget, returnData)


def tip(text):
    """Format a tooltip text: rich text, so Qt word-wraps long lines; '\\n' starts a new line."""
    if not text:
        return ""
    if text.lstrip().startswith("<"):
        return text
    return "<qt>" + html.escape(text).replace("\n", "<br>") + "</qt>"


_TOKENS_HINT = ("Tokens in {curly braces} are replaced per item - the 'All Tokens' "
                "spreadsheet column lists every token with its value.")
_ENV_HINT = "${VARIABLE} is replaced by the environment variable, e.g. ${USERNAME}."
_REGEX_HINT = ("Repl: optional result built from the regex groups, e.g. \\1_\\2, or a Python "
               "lambda: lambda m: m.group(1).upper(). Empty = the first group (or the whole match).")
_PARSE_HINT = ("Which text the regex runs on:\n"
               "File Name Only - just the file name\n"
               "Path Only - the folder path without the file name\n"
               "Full Path - folder path + file name\n"
               "Folder +N - the Nth folder below the Source Folder (+1 = first subfolder)\n"
               "Folder -N - the Nth folder counted up from the file (-1 = the file's own folder)")
_CAPS_HINT = ("How the parsed text is written: Keep Original, all lowercase, ALL UPPERCASE, "
              "PascalCase or snake_case.")
_BROWSE = "Pick the location in a file dialog instead of typing it."


# {class name: {attribute name: text}}. "__tabs__" maps a QTabWidget attribute to
# {tab text: text}.
TIPS = {
    # ------------------------------------------------------------------ top bar
    "TopBar": {
        "btn_folder": "Choose the folder with the footage to ingest. The folder is scanned "
                      "right away and its files appear in all panels.",
        "path_display": "The Source Folder currently scanned. Use 'Select Source Folder' to change it.",
        "chk_recursive": "On: subfolders of the Source Folder are scanned too.\n"
                         "Off: only the files directly in the Source Folder.",
        "btn_rescan": "Scan the Source Folder again - picks up new, removed and renamed files. "
                      "Your labels, AYON assignments and edits of existing files are kept.",
        "btn_reveal": "Open the Source Folder in the system file browser (Explorer).",
        "combo_preset": "Presets are complete IngestDesktop configurations (all Preferences) "
                        "stored in the Presets Folder. Picking one from the list loads it.",
        "btn_load_preset": "Load the preset selected in the list - replaces the current Preferences "
                           "with the preset's values.",
        "btn_save_preset": "Save the current Preferences as a named preset in the Presets Folder, "
                           "so you (or colleagues) can switch to this configuration later.",
        "btn_prefs": "Open Preferences: scanning, AYON, file categories and their presets, "
                     "conversions, pairing, CSV, grouping and more. Every control there has a tooltip.",
    },

    # ------------------------------------------------------------ canvas (main view)
    "ThumbnailArea": {
        "btn_frame_all": "Zoom and pan so every item is visible.\n"
                         "Hotkey: Z. Double-clicking empty space with nothing selected does the same.",
        "btn_frame_sel": "Zoom and pan so the selected items fill the view.\n"
                         "Hotkey: F. Double-clicking empty space while items are selected does the same.",
        "btn_show_text": "Show or hide the label under each thumbnail.",
        "btn_show_frames": "Show or hide the frames around the items (enabled / disabled / AYON "
                           "colors). Off: only selected items keep their frame - a clean view of "
                           "the images. The resize grip shows on selected items or on hover.",
        "btn_show_reviews": "Show review movies as separate items in this view - also reviews "
                            "paired with their footage by name (they are drawn below their main item).\n"
                            "Off by default: a paired review is reached through its main item.",
        "slider_text_size": "Label size, spring-loaded: drag right to make the labels bigger, "
                            "left to make them smaller. The knob springs back to the middle when "
                            "you let go, so you can drag again. Mouse wheel = small steps.",
        "slider_thumb_size": "Thumbnail size, spring-loaded: drag right to make the selected items "
                             "(or all visible items when nothing is selected) bigger, left to make "
                             "them smaller - each relative to its own size, so different sizes stay "
                             "different. The layout is kept: positions scale along, like zooming the arrangement. The knob springs back "
                             "to the middle when you let go. Mouse wheel = small steps.",
        "btn_player_mode": "Click to cycle the inline video player:\n"
                           "Player: Stop - no playback\n"
                           "Player: Selected - only the selected video plays\n"
                           "Player: All - every visible video plays (items stay selectable and movable)",
        "btn_paste": "Paste an image from the clipboard as a new file. It is saved into the "
                     "Clipboard temp folder (Preferences > Clipboard) and added to the view. Hotkey: Ctrl+V.",
        "btn_tag_filter": "Click to cycle which items are shown: All, Enabled only, Disabled only.\n"
                          "Disabled items are not published or converted.",
        "btn_queue": "Status of the thumbnail/review conversions. Click to open the Conversion "
                     "Queue (Ctrl+Q) to start, pause or check conversions.",
        "btn_maximize": "Hide the other panels to give this view all the space. Hotkey: Space.",
        "inline_editor": "Type the new label. Enter applies it, Esc cancels. Allowed characters are "
                         "set in Preferences > GUI.",
    },
    "ArrangeDialog": {
        "combo_sort": "Order in which the items are laid out.",
        "chk_reverse": "Reverse the sort order.",
        "chk_paired_follow": "Arrange only main items; each paired review is placed directly "
                             "below its main item instead of getting its own slot.",
        "slider_thumb_size": "Width of the thumbnails (pixels) after arranging.",
        "slider_cols": "Number of columns of the grid.",
        "chk_group_cols": "Put each group (items published together as one version, see "
                          "Preferences > Grouping) into its own column.",
        "slider_gap_h": "Horizontal space between items.",
        "slider_gap_v": "Vertical space between items.",
        "btn_ok": "Keep this arrangement and close.",
        "btn_cancel": "Put the items back where they were and close.",
    },
    "BackdropDialog": {
        "label_edit": "Big text drawn on the backdrop (e.g. a shot or sequence name).",
        "label_size": "Font size of the backdrop label.",
        "label_color_btn": "Color of the backdrop label. Click to pick.",
        "chk_bold": "Bold label.",
        "chk_italic": "Italic label.",
        "chk_strike": "Struck-through label.",
        "chk_underline": "Underlined label.",
        "alignment_combo": "Where in the backdrop the label is drawn.",
        "name_edit": "Name of the backdrop as listed in the file panel (when 'Files' is off).",
        "radio_border": "Draw the backdrop as an outline only.",
        "radio_fill": "Draw the backdrop as a filled rectangle.",
        "border_color_btn": "Outline color. Click to pick.",
        "fill_color_btn": "Fill color. Click to pick.",
        "btn_done": "Apply the changes and close.",
        "btn_apply": "Apply the changes and keep the dialog open.",
    },
    "NoteToolbar": {
        "btn_bold": "Bold - applies to the selected text, or to the whole note when nothing is selected.",
        "btn_italic": "Italic - applies to the selected text, or to the whole note.",
        "btn_underline": "Underline - applies to the selected text, or to the whole note.",
        "btn_strike": "Strike-through - applies to the selected text, or to the whole note.",
        "btn_color": "Text color - applies to the selected text, or to the whole note.",
        "btn_bg_color": "Background color of the note.",
        "spin_size": "Font size - applies to the selected text, or to the whole note.",
    },
    "SequenceRenameDialog": {
        "prefix": "Text at the start of every new label.",
        "chk_add_counter": "Add a running number after the prefix, so every label is unique.",
        "counter_start": "Number of the first item.",
        "counter_zeroes": "Digits of the counter, padded with zeroes (3 -> 001, 002...).",
        "suffix": "Text at the end of every new label.",
        "btn_ok": "Rename the labels of the selected items (in their current order). "
                  "Files on disk are not renamed.",
        "btn_cancel": "Close without renaming.",
    },
    "RenameDialog": {
        "edit": "The new text.",
        "btn_ok": "Apply the new text.",
        "btn_cancel": "Close without changes.",
    },
    "SearchReplaceDialog": {
        "search_edit": "Text to find in the labels of the selected items.",
        "replace_edit": "Text that replaces it (can be empty to remove the text).",
        "btn_ok": "Replace every occurrence in the labels of the selected items.",
        "btn_cancel": "Close without changes.",
    },

    # ------------------------------------------------------------ spreadsheet
    "SpreadsheetPanel": {
        "btn_selected_only": "Show only the rows of items selected in the main view or the file panel.",
        "btn_tagged_only": "Show only enabled items (the ones that will be published).",
        "btn_assigned_only": "Show only items that have an AYON folder and task assigned.",
        "btn_show_grouped": "Sort rows so items published together (same group, see Preferences > "
                            "Grouping) are next to each other.",
        "btn_show_reviews": "Show review movies as rows - each paired review is listed right below "
                            "its main file, in magenta. Its AYON path, variant, version and comment "
                            "come from the main file (edit them there).",
        "btn_check_ver_only": "Compare the versions with AYON and mark the ones that already exist "
                              "(orange). Nothing is changed.",
        "btn_check_ver": "Compare the versions with AYON and fix the ones that already exist, as "
                         "set in Preferences > General > Version Collision.",
        "btn_check_dup": "Highlight items that would be published to the same place (same Duplicate "
                         "Identity, Preferences > AYON).",
        "btn_tag_sel": "Enable / disable the selected items. Disabled items are not published or "
                       "converted. Hotkey: Ctrl+D.",
        "btn_csv": "Switch the table to a preview of the CSV that will be exported (columns from "
                   "Preferences > CSV).",
        "slider_row_height": "Row height - taller rows show bigger thumbnails.",
        "btn_replace": "Write the text on the right into the chosen field of all selected rows.",
        "comment_field": "Text written into the chosen field of the selected rows by 'Replace:'.",
        "combo_replace_field": "Which field 'Replace:' writes to: Comment, Variant User or Version User.",
    },

    # ------------------------------------------------------------ file panel
    "FilterPanel": {
        "chk_search": "Turn the search filter on/off without clearing its text.",
        "search_bar": "Show only files whose name contains this text. Items filtered out are grey "
                      "here and hidden in the other views.",
        "chk_ignore": "Turn the ignore filter on/off without clearing its text.",
        "ignore_bar": "Hide files whose path contains any of these words (space separated).",
        "chk_age": "Turn the age filter on/off.",
        "spin_age": "Show only files younger than this. The date used (modified or created) is set "
                    "in Preferences > General.",
        "combo_units": "Unit of the age filter.",
        "btn_files_only": "On: list files. Off: list the canvas backdrops and notes instead "
                          "(right-click them to edit or delete).",
        "btn_flat": "One flat list of all files instead of the folder tree.",
        "btn_unfold": "Expand every folder in the tree.",
        "btn_v_stack": "Collapse versions of the same file: only the highest version is shown "
                       "(right-click to pick another).",
        "btn_sequences": "Show image sequences as one entry instead of one entry per frame.",
        "btn_show_reviews": "Show review movies in the file list - also reviews paired with footage "
                            "by name (in magenta). Off by default.",
    },

    # ------------------------------------------------------------ AYON panel
    "AyonPanel": {
        "combo_project": "AYON project to work with. Its folders and tasks are listed below.",
        "btn_refresh": "Read the folders, tasks and products from AYON again.",
        "btn_auto": "Assign AYON folders and tasks to the items automatically, from their file "
                    "names / paths (rules in Preferences > Auto-Assign).",
        "search_edit": "Filter the tree. What is searched is chosen on the right.",
        "search_combo": "Search by folder/task Name, task Type, Status or Assignee.",
        "btn_assigned_only": "Show only folders and tasks that some items are assigned to.",
        "btn_show_thumbs": "Show AYON thumbnails in the tree.",
        "btn_clear_all": "Remove the AYON folder and task assignment from all items.",
        "btn_show_representations": "Show the representations (files) of the product selected above.",
        "btn_hide_products": "Hide / show the products list to give the tree more space.",
        "combo_product_types": "Show only products of the checked types.",
        "chk_collapse_repre": "Show only the highest version of each representation.",
    },
    "TaskStatusDialog": {
        "chk_same_task": "Also set the task to the status you pick.",
    },

    # ------------------------------------------------------------ main window
    "MainWindow": {
        "chk_check_versions": "Before Export / Publish, check the versions against AYON and stop when "
                              "an item's version is not higher than the existing one.",
        "chk_check_duplicates": "Before Export / Publish, stop when two items would be published to "
                                "the same place (same Duplicate Identity).",
        "btn_export_csv": "Write the CSV of all enabled items (format in Preferences > CSV). It can be "
                          "published with AYON Traypublisher.",
        "btn_publish_local": "Export the CSV and publish it with AYON Traypublisher on this computer. "
                             "Afterwards checks the result, writes the Ingest Log/Report and sets "
                             "statuses (Preferences > AYON).",
        "btn_publish_deadline": "Send the review conversions of all items that need a review to "
                                "the Deadline render farm (settings in Preferences > Deadline).",
        "btn_toggle_log": "Show / hide the log. Drag its top edge to resize; right-click it to "
                          "clear or change how much is logged.",
    },
    "LogPanel": {
        "console": "Messages of the app. Right-click: Clear, Verbosity (minimal / normal / verbose). "
                   "Drag the top edge to resize.",
    },

    # ------------------------------------------------------------ conversion queue
    "ConversionQueueDialog": {
        "btn_convert_reviews": "Create review movies for the items that need one and don't have it yet.",
        "btn_force_convert_reviews": "Create review movies again, also where one already exists.",
        "btn_convert_thumbs": "Create thumbnails for items that don't have one yet.",
        "btn_force_convert_thumbs": "Create thumbnails again, also where one already exists.",
        "btn_check_existing": "Check which review files exist on disk now (e.g. after farm processing) "
                              "and update the statuses.",
        "chk_selected_only": "List (and convert) only the items selected in the main view.",
        "btn_pause": "Pause / resume the running conversions.",
        "btn_cancel": "Stop the conversions and close this window.",
        "btn_restart": "Reset done/failed/running reviews to waiting and start the conversions again.",
    },

    # ------------------------------------------------------------ video player
    "VideoPlayerPanel": {
        "timeline_slider": "Drag to move through the video.",
        "volume_slider": "Volume.",
        "btn_stop": "Stop and go back to the start.",
        "btn_mute": "Mute / unmute.",
        "btn_system_launch": "Open the video in the default system player.",
        "btn_fallback_play": "Open the video in the default system player (the inline player is "
                             "not available in this installation).",
    },

    # ------------------------------------------------------------ preferences
    "PreferencesDialog": {
        "__tabs__": {"tabs": {
            "General": "Folders, sessions, scanning, version collisions, ingest report.",
            "AYON": "Server, publishing via Traypublisher, ingest check and statuses.",
            "AYON Items": "What is fetched when you pull existing AYON products into the view.",
            "Auto-Assign": "How AYON folder, task, variant... are parsed from file names.",
            "CSV": "Format and columns of the exported CSV.",
            "Conversions": "Thumbnail/review conversion: commands, locations, tool paths.",
            "Pairing": "Linking existing thumbnails and reviews to their footage by name.",
            "Clipboard": "Where pasted images are saved.",
            "GUI": "View defaults and item tooltips.",
            "Stills": "Single images: extensions and presets.",
            "File Sequences": "Numbered image sequences: extensions and presets.",
            "Video Containers": "Movie files: extensions and presets.",
            "Other": "Other files (workfiles, cameras, models...): extensions and presets.",
            "Grouping": "Which items are published together as one version.",
            "Secrets": "API keys - stored only on this computer.",
            "Deadline": "Render farm settings for review processing.",
        }},
        # General
        "default_scan_folder": "Folder scanned when the app starts (if no last session is loaded). "
                               + _ENV_HINT,
        "btn_browse_scan": _BROWSE,
        "presets_folder": "Where named presets (complete configurations) are stored. A shared "
                          "network folder lets the team use the same presets. " + _ENV_HINT,
        "btn_browse_presets": _BROWSE,
        "ingest_log_folder": "Where Ingest Logs (CSV, one line per published item) and Ingest "
                             "Reports (PDF) are written. " + _ENV_HINT,
        "btn_browse_log": _BROWSE,
        "per_project_logging": "Write logs into a subfolder named after the AYON project.",
        "sessions_folder": "Your last session (project 'last') is saved here every time the app "
                           "exits. " + _ENV_HINT + " Example: //server/ingest/sessions/${USERNAME}",
        "btn_browse_sessions": _BROWSE,
        "load_last_session": "On start, reopen the last session: folder, items, labels, AYON "
                             "assignments, canvas layout and panel states.",
        "age_source": "Which file date the Age filter uses.",
        "detect_sequences": "Group numbered images (shot.1001.exr, shot.1002.exr...) into one sequence item.",
        "ver_collision_fail": "When a version already exists in AYON: refuse to publish it and mark "
                              "it orange in the spreadsheet.",
        "ver_collision_lowest": "When a version already exists in AYON: change it to the lowest "
                                "version that is still free.",
        "create_ingest_report": "After publishing, create a PDF report (A4 landscape) of what was "
                                "ingested, in the Ingest Log Folder.",
        "timezone_offset_a": "Your UTC offset (e.g. +01:00), shown in the Ingest Report.",
        "timezone_offset_b": "The client's UTC offset (e.g. -08:00), shown in the Ingest Report.",
        "play_sounds": "Play a system sound when confirmation dialogs appear (settings saved, "
                       "preset saved, export, ingest finished).",
        # AYON
        "server_url": "Address of your AYON server, e.g. https://ayon.studio.com",
        "traypublisher_path": "ayon_console.exe (or ayon.exe) used to run Traypublisher for "
                              "'Publish Ayon Local'.",
        "btn_browse_console": _BROWSE,
        "product_name": "Template of the AYON product name, e.g. {label} or {product_type}{variant}. "
                        + _TOKENS_HINT,
        "product_name_camel": "camelCase the product name: every token after the first starts with "
                              "a capital letter (plate + Main -> plateMain).",
        "duplicate_identity": "Template that identifies where an item is published. Two enabled "
                              "items with the same result are duplicates. " + _TOKENS_HINT,
        "ayon_project_name": "Default AYON project.",
        "csv_ingest_folder": "AYON folder used by the Traypublisher CSV ingest. It must exist in the project.",
        "csv_ingest_task": "Task in that folder used by the CSV ingest. It must exist.",
        "csv_preset": "Name of the CSV ingest preset in the AYON project settings.",
        "ignore_validators": "Publish even when Traypublisher validators (e.g. frame range) complain.",
        "ingest_check": "After publishing, check in AYON that the versions really exist; items get "
                        "a green (ok) or red (failed) mark.",
        "get_ayon_thumbnails": "Download AYON thumbnails for the tree and AYON items.",
        "ayon_thumbnails_cache": "Folder where downloaded AYON thumbnails are cached.",
        "btn_browse_cache": _BROWSE,
        "ayon_version_status": "Status given to the published versions (e.g. Pending Review).",
        "set_version_status_after_check": "After the Ingest Check, set the versions to the status above.",
        "set_product_status_after_check": "After the Ingest Check, set the products to the same status.",
        "set_task_status_after_check": "After the Ingest Check, set the tasks to the same status.",
        "set_neighbour_status_after_check": "After the Ingest Check, set the status of another task "
                                            "in the same folder (e.g. let comp know new plates arrived).",
        "neighbour_task_name": "Name of the neighbour task, e.g. comp.",
        "neighbour_task_status": "Status for the neighbour task, e.g. Ready to start.",
        # AYON Items
        "ayon_item_task_type_priority": "When pulling AYON items into the view: task types to "
                                        "prefer, in order (space separated).",
        "ayon_item_task_name_priority": "Task names to prefer, in order (space separated).",
        "ayon_item_product_type_priority": "Product types to prefer, in order (space separated).",
        "ayon_item_product_name_priority": "Product names to prefer, in order (space separated).",
        "ayon_item_product_version": "Which version to take: the highest, the lowest, the highest "
                                     "with the status below (else the highest), or only one with that status.",
        "ayon_item_product_version_status": "Status used by the 'by Status' version modes.",
        "ayon_item_repre_priority_extension": "Representations to prefer, by extension, in order "
                                              "(e.g. mp4 mov png).",
        "ayon_item_label": "Label of an AYON item in the view. " + _TOKENS_HINT,
        "item_info_ayon": "Text of the hover info of AYON items. " + _TOKENS_HINT,
        # Auto-Assign
        "version_parse": _PARSE_HINT,
        "version_regex": "Regex that finds the version; the last group is the number. "
                         "Example: ([._]v|v)(\\d+)",
        "version_repl": _REGEX_HINT,
        "folder_parse": _PARSE_HINT,
        "folder_regex": "Regex that finds the AYON folder (shot/asset) name -> {folder_name}. "
                        "Example: ^([^_]*_[^_]*)_.*$ takes 'sq010_sh020' from sq010_sh020_comp_v001.exr",
        "folder_repl": _REGEX_HINT,
        "folder_capitalization": _CAPS_HINT,
        "task_parse": _PARSE_HINT,
        "task_regex": "Regex that finds the task name -> {task_name}.",
        "task_repl": _REGEX_HINT,
        "task_capitalization": _CAPS_HINT,
        "fixed_task_name_enabled": "Always use the task name on the right instead of parsing it.",
        "fixed_task_name": "Task name used for every item when 'Fixed Task Name' is on.",
        "variant_parse": _PARSE_HINT,
        "variant_regex": "Regex that finds the variant -> {variant_parsed}.",
        "variant_repl": _REGEX_HINT,
        "variant_capitalization": _CAPS_HINT,
        "sequence_parse": _PARSE_HINT,
        "sequence_regex": "Regex that finds the sequence -> {sequence}.",
        "sequence_repl": _REGEX_HINT,
        "sequence_capitalization": _CAPS_HINT,
        "episode_parse": _PARSE_HINT,
        "episode_regex": "Regex that finds the episode -> {episode}.",
        "episode_repl": _REGEX_HINT,
        "episode_capitalization": _CAPS_HINT,
        "auto_assign_multi_match": "If the parsed name matches more than one AYON folder, take the "
                                   "first one instead of leaving the item unassigned.",
        "auto_assign_fallback_task": "If the folder is found but the task is not, assign the folder's "
                                     "first task instead of leaving the item unassigned.",
        # CSV
        "csv_delimiter": "Character between the CSV columns, usually a comma.",
        "csv_quotechar": "Character around values that contain the delimiter, usually \".",
        "csv_columns": "One column per line: Header=Value. The value is a template, e.g. "
                       "Version={version}. " + _TOKENS_HINT,
        # Conversions
        "run_thumb_after_scan": "Start creating thumbnails as soon as a scan finishes.",
        "run_review_after_scan": "Start creating review movies as soon as a scan finishes.",
        "skip_existing_thumbs": "Don't create a thumbnail when its file already exists.",
        "skip_existing_reviews": "Don't create a review when its file already exists.",
        "default_fps": "Frame rate used when a file has none (or metadata is not used).",
        "use_fps_from_metadata": "Read the frame rate from the file's metadata when available.",
        "seq_thumb_frame": "Which frame of a sequence becomes its thumbnail.",
        "high_res_size": "Size of the created thumbnails. Token: {prefs_highres_thumb_size}",
        "thumb_location": "Where thumbnails are written: next to the file, in a folder relative to "
                          "the Source Folder, or in a custom folder.",
        "thumb_location_path": "Folder name (relative) or full path (custom) for thumbnails. "
                               "Together with suffix and format it forms {prefs_thumb_path}.",
        "thumb_suffix": "Added to the file name of the thumbnail (shot_v001_thumbnail.jpg).",
        "thumb_format": "File format of the thumbnails.",
        "thumb_quality": "JPG quality of the thumbnails (higher = better, bigger).",
        "cmd_stills": "Command that creates the thumbnail of a still. Category presets can "
                      "override it. " + _TOKENS_HINT,
        "cmd_videos": "Command that creates the thumbnail of a video. " + _TOKENS_HINT,
        "cmd_sequences": "Command that creates the thumbnail of a sequence. " + _TOKENS_HINT,
        "ffmpeg_path": "ffmpeg executable. Token: {ffmpeg}",
        "btn_browse_ffmpeg": _BROWSE,
        "ffprobe_path": "ffprobe executable (reads video metadata). Token: {ffprobe}",
        "btn_browse_ffprobe": _BROWSE,
        "oiiotool_path": "OpenImageIO oiiotool executable. Token: {oiiotool}",
        "btn_browse_oiio": _BROWSE,
        "vfxtranscode": "VFX Transcode executable. Token: {vfxtranscode}",
        "btn_browse_vfx": _BROWSE,
        "ocio_config": "OCIO config used for color conversions. Token: {ocio_config}",
        "btn_browse_ocio": _BROWSE,
        "timeout_seconds": "A conversion that runs longer than this is cancelled. 0 = no limit.",
        # Pairing (the other Pairing controls keep the tooltips set in prefs_dialog)
        "pair_mode_same": "Pair only files with exactly the same name (extension aside): "
                          "shot_v001.exr + shot_v001.mp4.",
        # Clipboard
        "clip_temp_root": "Folder where pasted images are saved. " + _ENV_HINT,
        "clip_folder_template": "Subfolder for pasted images. {yy} {mm} {dd} = today's date.",
        "clip_file_prefix": "File name of pasted images, followed by a counter.",
        "clip_file_counter": "Digits of the counter in pasted file names (3 -> clipboard_001.png).",
        # GUI
        "default_cols": "Number of columns of the main view after a scan.",
        "default_text_size": "Label font size in the main view after a scan.",
        "default_thumb_size": "Thumbnail size in the main view after a scan.",
        "label_regex": "Regex of the characters allowed in labels. A label that doesn't match is refused.",
        "edge_swipe_panels": "Move the mouse quickly out over the left, right or bottom edge of the "
                             "window to hide or show the AYON, file or spreadsheet panel. A movement "
                             "that carries on to another screen doesn't count.",
        "disable_inline_video": "Never play videos inside the app; always open them in the system player.",
        "drawing_cache_location": "Where drawings made on thumbnails are stored.",
        "drawing_cache_path": "Folder name (relative) or full path (custom) for drawings.",
        "item_info_generic": "Text of the hover info of items without their own (Category tabs). "
                             + _TOKENS_HINT,
        # Grouping
        "group_by": "Items with the same result of this template are one group: published together "
                    "as one AYON version with several representations. " + _TOKENS_HINT,
        "group_do_not_export_missing_repres": "Skip a whole group on export when a representation "
                                              "its group definition requires is missing.",
        # Secrets
        "api_key": "AYON API key (service user). Stored only on this computer.",
        "ftrack_server": "Ftrack server URL. Passed to Traypublisher as environment variable.",
        "ftrack_user": "Ftrack API user.",
        "ftrack_key": "Ftrack API key.",
        # Deadline
        "deadline_job_name": "Name of the farm jobs. " + _TOKENS_HINT,
        "deadline_department": "Deadline department of the jobs.",
        "deadline_pool": "Deadline primary pool.",
        "deadline_secondary_pool": "Deadline secondary pool.",
        "deadline_group": "Deadline group (machines allowed to render).",
        "deadline_priority": "Job priority (0-100, higher first).",
        "deadline_machine_limit": "How many machines may work on one job at once (0 = no limit).",
        "deadline_concurrent_tasks": "Tasks one machine runs at the same time.",
        # buttons
        "btn_save": "Save the Preferences and close.",
        "btn_apply": "Use the Preferences now and keep this window open.",
        "btn_cancel": "Close without saving changes.",
    },
    "PresetWidget": {
        "btn_toggle": "Preset on / off. An off preset is never used to match files.",
        "btn_up": "Move up = higher priority. The first enabled preset whose filter matches a file is used.",
        "btn_down": "Move down = lower priority.",
        "name": "Name of the preset (only for you).",
        "filter_by": "What the filter is compared with: the file Extension, file Name, Path or item Label.",
        "filter_str": "Text that must be contained to use this preset (e.g. exr, _plate_). Empty = matches everything.",
        "product_type": "AYON product type for files of this preset.",
        "variant": "AYON variant, e.g. Main or {label}. " + _TOKENS_HINT,
        "camel_case": "camelCase the variant (every token after the first starts with a capital).",
        "fps_override": "Use the FPS on the right for these files.",
        "fps": "Frame rate used when 'FPS Override' is on.",
        "fps_from_metadata": "Read the frame rate from the file's metadata when available.",
        "slate_exists": "The first frame is a slate (not part of the shot).",
        "handle_start": "Handle frames at the start of the clip.",
        "handle_end": "Handle frames at the end of the clip.",
        "representation": "AYON representation name, e.g. exr or {extension}.",
        "rep_tags": "AYON representation tags, separated by ;",
        "colorspace": "OCIO colorspace of the files, e.g. ACES - ACEScg.",
        "convert_thumb": "Create a thumbnail for these files.",
        "convert_thumb_override": "Use the command below instead of the one in Preferences > Conversions.",
        "convert_thumb_cmd": "Thumbnail command for this preset. " + _TOKENS_HINT,
        "convert_review": "Create a review movie for these files.",
        "review_location": "Where the review is written: next to the file, relative to the Source "
                           "Folder, or in a custom folder.",
        "review_path": "Folder name (relative) or full path (custom) for reviews.",
        "review_suffix": "Added to the review file name (shot_v001_review.mp4).",
        "review_format": "File format of the review, e.g. .mp4",
        "review_representation": "AYON representation name of the review, e.g. h264.",
        "review_colorspace": "Colorspace of the review.",
        "review_rep_tags": "AYON tags of the review representation, separated by ;",
        "convert_review_cmd": "Command that creates the review. " + _TOKENS_HINT,
    },
    "GroupWidget": {
        "btn_toggle": "Fold / unfold this group definition.",
        "enabled": "Use this group definition. The first enabled definition that matches a group is used.",
        "btn_up": "Move up = higher priority.",
        "btn_down": "Move down = lower priority.",
        "name": "Name of the group definition (only for you).",
        "task_types": "Use this definition for groups with one of these task (or product) types. "
                      "Space separated, empty = any.",
        "task_names": "Use this definition for groups with one of these task names. Space separated, empty = any.",
        "always_repres": "Representations that must be in the group as files (space separated, e.g. exr).",
        "always_or_convert_repres": "Representations that must be in the group, as files or created "
                                    "by conversion (e.g. jpg thumbnail, h264 review).",
        "optional_repres": "Representations that may be in the group but are not required.",
        "inheritance_priority": "Order of representations used as the source when values are "
                                "inherited (e.g. exr mov). Space separated.",
        "review_repre": "Representation(s) used as the review of the group.",
        "thumb_source_repre": "Representation whose thumbnail is used for the whole group.",
        "inherit_columns": "Columns copied from the highest-priority item to items where they are "
                           "empty (space separated, e.g. comment colorspace).",
    },
}

# Category tab widgets that are local variables in PreferencesDialog
CATEGORY_TIPS = {
    "ext_field": "File extensions of this category, space separated (e.g. .exr .dpx). "
                 "A file sequence with one frame counts as a still.",
    "item_info": "Text of the hover info of items in this category. " + _TOKENS_HINT,
    "stills_thumb_cb": "Use the image itself as its thumbnail (no conversion).",
    "start_f": "First frame given to items of this category.",
    "end_f": "Last frame given to stills.",
    "video_tc_cb": "Take the start frame from the video's timecode.",
    "btn_add": "Add a new preset to this category.",
    "btn_delete": "Delete the selected preset (click a preset to select it).",
    "btn_duplicate": "Copy the selected preset (click a preset to select it).",
    "btn_group_add": "Add a new group definition.",
    "btn_group_delete": "Delete the selected group definition.",
}


def _labels_follow_fields(owner):
    """Give a form/grid/row label the tooltip of the field next to it (if it has none)."""

    def field_tip(item):
        if item is None:
            return ""
        w = item.widget()
        if w is not None:
            if w.toolTip():
                return w.toolTip()
            lay = w.layout()
        else:
            lay = item.layout()
        if lay is not None:
            for i in range(lay.count()):
                t = field_tip(lay.itemAt(i))
                if t:
                    return t
        return ""

    def give(label_item, tip_text):
        if label_item is None or not tip_text:
            return
        lbl = label_item.widget()
        if isinstance(lbl, QLabel) and not lbl.toolTip():
            lbl.setToolTip(tip_text)

    for form in owner.findChildren(QFormLayout):
        for row in range(form.rowCount()):
            give(form.itemAt(row, QFormLayout.LabelRole),
                 field_tip(form.itemAt(row, QFormLayout.FieldRole)))
    for grid in owner.findChildren(QGridLayout):
        for row in range(grid.rowCount()):
            for col in range(grid.columnCount() - 1):
                give(grid.itemAtPosition(row, col), field_tip(grid.itemAtPosition(row, col + 1)))
    for box in owner.findChildren(QBoxLayout):
        for i in range(box.count() - 1):
            give(box.itemAt(i), field_tip(box.itemAt(i + 1)))


def apply(owner):
    """Set the tooltips of `owner` from TIPS (looked up by the class names of its MRO)."""
    for cls in reversed(type(owner).__mro__):
        tips = TIPS.get(cls.__name__)
        if not tips:
            continue
        for attr, text in tips.items():
            if attr == "__tabs__":
                for tabs_attr, by_title in text.items():
                    tabs = getattr(owner, tabs_attr, None)
                    if isinstance(tabs, QTabWidget):
                        for i in range(tabs.count()):
                            t = by_title.get(tabs.tabText(i).replace("&", ""))
                            if t:
                                tabs.setTabToolTip(i, tip(t))
                continue
            w = getattr(owner, attr, None)
            if isinstance(w, QWidget):
                w.setToolTip(tip(text))
    if isinstance(owner, QWidget):
        _labels_follow_fields(owner)


def _wrap_init(cls):
    if getattr(cls.__init__, "_tooltips_wrapped", False):
        return
    orig = cls.__init__

    def __init__(self, *args, **kwargs):
        orig(self, *args, **kwargs)
        if type(self) is cls:  # once, after the most derived __init__ finished
            try:
                apply(self)
            except Exception:  # tooltips must never break the UI
                import logging
                logging.debug("tooltips: apply failed for %s", cls.__name__, exc_info=True)

    __init__._tooltips_wrapped = True
    cls.__init__ = __init__


def install_all():
    """Wrap the GUI classes so their instances get tooltips. Call once before building the UI."""
    import importlib
    modules = ["gui.top_bar", "gui.thumbnail_area", "gui.spreadsheet_panel", "gui.filter_panel",
               "gui.ayon_panel", "gui.main_window", "gui.log_panel", "gui.conversion_queue_dialog",
               "gui.video_player", "gui.prefs_dialog", "gui.preset_widget", "gui.group_widget",
               "gui.canvas.widgets", "gui.window.dialogs"]
    for name in modules:
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue
        for cls_name in TIPS:
            cls = getattr(mod, cls_name, None)
            if isinstance(cls, type) and cls.__module__ == mod.__name__:
                _wrap_init(cls)
