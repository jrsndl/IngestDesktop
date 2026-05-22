# IngestDesktop — User Manual & Quickstart Reference

Welcome to the user guide for **IngestDesktop**, a professional desktop application designed to catalog, validate, and deliver digital media assets to production pipelines, including **AYON** databases and local or remote render farms.

---

## 🚀 Quickstart Guide

Get up and running with IngestDesktop in four simple steps.

![Quickstart Pipeline Infographic](resources/ingest_desktop_quickstart.png)

### 1. Scan and Import
Use the **Top Bar** to browse or paste a local directory path. IngestDesktop indexes the folder, categorizes files, extracts dimensions, frame counts, and codecs, and populates the thumbnail grid.

### 2. Auto-Assign Metadata via Presets
Extract metadata tokens from folder structures and filenames using pattern recognition:
* **Named & User Presets**: In the Preferences dialog under the Auto-Assign tab, you can load predefined named presets or save your own custom user patterns.
* **Auto-Assign Trigger**: Click **Auto-Assign** to run the active pattern matching. This populates fields such as Folder Name, Task Name, Sequence, and Episode.

### 3. Verify and Edit AYON Paths
* **Manual AYON Path Assignment**: If automated templates do not match your assignment rules, you can double-click and manually enter or edit the target AYON database path directly within the spreadsheet table rows.
* **Validation Check**: Trigger the Ingest Check to verify version stack collisions, check duplicate labels, and ensure database structures line up before submission.

### 4. Process Reviews (Local or Deadline)
Send review files to local workers or offload them directly to the **Deadline Render Farm** with a single click.

---

## 🛠️ Feature Reference & Capabilities

````carousel
![Conversion Panel UI Screenshot](resources/conversions_deadline_panel.png)
<!-- slide -->
```markdown
# Supported Substitution Tokens
Use these tokens inside Job Name templates or transcode targets:
* {ffmpeg}      -> Windows FFMpeg Path
* {ffprobe}     -> Windows FFProbe Path
* {oiiotool}    -> Windows OIIOTool Path
* {vfxtranscode} -> Windows VFX Transcode Path
* {label}       -> Custom asset identifier (e.g. comp, plate)
* {ayon_path}   -> Asset project target path
```
````

### 📁 Filter Panel
The **Filter Panel** located on the left provides flexible navigation options for scanned assets:
* **Hierarchical View**: Navigate your scanned files via a standard directory folder tree.
* **Flat View**: Switch to a unified, alphabetical flat list of all project files, ideal for quick sorting.
* **Toggles**:
  * *Files Only*: Hide or show scene backdrops and notes.
  * *Version Stack*: Filter entries to show only the highest parsed version string.
  * *Sequences*: Collapse image sequences into a single representative sequence asset with start/end frames noted.

### 🎬 Video Playback & Controls
IngestDesktop features a built-in video player overlay for quick reviews:
* **Playback Controls**: Hover or click video thumbnails to trigger instant loop playbacks. Press **Spacebar** to toggle play/pause, or **M** to toggle audio muting.
* **Tri-State Player Modes**: Use the button in the controls header to select:
  * *Player: Selected*: Only the currently selected video thumbnail plays.
  * *Player: All*: All visible video cards in the viewport play simultaneously.
  * *Player: Stop*: Playback is entirely disabled, clearing all active media resources.

### 📐 Layout Management, Backdrops & Notes
Organize and annotate your graphics workspace:
* **Arrange Grid**: Use the columns spinner and thumb size sliders in the controls header to customize item scale and grid spacing on the fly.
* **Backdrops**: Group thumbnails visually by placing resizable backdrop panels in the scene.
* **Text Notes**: Place notes directly in the canvas for layout annotations or ingestion logs.

### ✏️ Thumbnail Batch Renaming
* Select multiple thumbnails and right-click to open the sequence renaming tools.
* Configure prefix naming patterns, start indexes, zero-padding counters, and suffix tags to batch-update target spreadsheet labels instantly.

### 🔍 Post-Ingest Validation, Logs & PDF Reports
Protect your pipeline against corrupted files and configuration mismatches:
* **Post-Ingest Validation**: The validation engine automatically verifies local file sizes, generates md5 hashes, checks for duplicate naming tokens, and flags version overlaps.
* **Ingest Log & Report**:
  * *CSV Log*: Generates a raw action-history log detailing validation passes and failures.
  * *PDF Report*: Compiles a beautifully formatted A4 Landscape Ingest Report PDF including embedded image thumbnails (preserving native aspect ratios), success filters, and normalized local/client time stamps (based on configurable timezone offsets).

---

### 🎹 Workspace Hotkeys & Shortcuts

| Keyboard Action | Scope / Mode | Result |
| :--- | :--- | :--- |
| **`Double-Click` (Thumbnail)** | Grid View | Pans and zooms to frame the selected item in the viewport. |
| **`Double-Click` (Video overlay)** | Grid View / Playing | Frames the selected item and ensures loop playback resumes. |
| **`F5`** | Global Workspace | Triggers a full disk-level directory rescan and updates cache. |
| **`Spacebar`** | Video Player | Toggles video playback (play / pause) on active overlays. |
| **`M`** | Video Player | Toggles the mute state of the active review player. |

---

> [!NOTE]
> All visual assets, infographics, and status indicators in this documentation are designed for dark-theme desktop layouts.
