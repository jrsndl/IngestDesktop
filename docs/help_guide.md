# IngestDesktop — User Manual & Quickstart Reference

Welcome to the user guide for **IngestDesktop**, a desktop application designed to catalog, validate, and ingest files to **AYON** pipeline.

---

## 🚀 Quickstart Guide

Get up and running with IngestDesktop in four simple steps.

![Quickstart Pipeline Infographic](resources/ID_ss01.png)

### 1. Folder Scan
Use the **Top Bar** to browse or drag & drop a local directory path. IngestDesktop indexes the folder, categorizes files and populates the thumbnail grid, displaying widely supported image and video files right away. You can limit the files by text search or age filtering.
You can also just paste images from the clipboard: this mode saves the images to the temp folder; suitable for hunting references or working with cloud AI.

### 2. Metadata Extraction
IngestDesktop uses ffprobe to extract metadata like image resolution or timecode.

### 3. Conversions
IngestDesktop can be configured to do two conversions for every item found in the scanned folder. Thumbnail conversion produces still image. Review conversion typically produces lightweight video output like H264 in mp4 container. The Review conversions might be taxing, you can offload the processing to Deadline farm.
By default, IngestDesktop skips the processing of existing files. Video files playable by ffplay can be played directly at the Thumbnail view; use Play control toggle to play all, selected or no videos.

### 4. Assigning AYON Folder and Task
IngestDesktop connects to AYON server, and offers user to assign the folder & taks by doubleclicking item from the list. Another option relies on naming convention, you can use regular expressions to parse file names and auto assign AYON folder and task by name.
The AYON panel also shows list of produucts and thheir representations.

### 5. Assigning AYON Product Name from Label
IngestDesktop initially sets the label for each item as a file name stripped of version (and file counter in case the item is an image sequence). Thumbnnail view context menu or F2 hotkey offers many ways to rename the item labels.
Label is used to construct the AYON Product Name. Alternatively, user can assign already used product name pulled from AYON database by doubleclicking it.

### 6. Validating Versions
IngestDesktop parses the version from the file name, or assigns default v1. Version can be user edited in the Spreadsheet view. Version check is performed before sending files to AYON, or by user pressing the Version Check & Fix button.

### 7. Marking items for ingest
User can mark the items to be enabled or disabled, to control which items will be send to AYON. Hotkey Ctrl+D

### 8. Publish Files
Publish AYON local button creates CSV file for AYON Traypublisher, checks versions and duplicities, and publishes enabled items.

### 9. Log, Status change and Report after Publish.
After publishing, IngestDesktop reloads the AYON panel, and checks that every row in the CSV spreadsheet is present in the AYON database.
Cuccesful publishes are marked with green corner in the Thumbnail view and check mark in the File panel. There is also Ingest Status column in the Spreadsheet view.
The result is logged to CSV file. You can optionally set the status of the published version in AYON. Another feature is Neighbour Task Status: for example, after ingesting a CG render, you might want to set the compositing task status to "Ready to Start".
IngestDesktop can also generate simple PDF with ingest report.


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

