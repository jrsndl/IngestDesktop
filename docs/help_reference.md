# IngestDesktop — System Reference Encyclopedia

This reference guide provides an exhaustive description of every interface panel, visual indicator, context menu, top control, and configuration tab available within **IngestDesktop**.

> [!NOTE]
> **Documentation Visuals Disclaimer**: The illustrations and interface layout graphics included in this user guide are functional conceptual diagrams designed to explain the asset pipeline visually. They are not direct live viewport frames.

---

## 🎛️ 1. Workspace Panels & Detailed Controls

### 🗺️ Top Bar (Navigation & Globals)
The control header at the very top of the application manages directory targets, scanning, and global timezones:
* **Source Folder input field**: Displays the currently scanned local or network directory path. Can be edited manually.
* **Browse button (`...`)**: Opens a native system folder dialog to select a source directory.
* **Rescan button (`F5` icon)**: Forces a full disk-level scan of the directory, rebuilding thumbnails, caches, and metadata indexes.
* **Clipboard Status indicator**: Displays state information when pasting clipboard imagery.
* **Timezone Markers**: Displays App Local Time A and Client Time B (derived via timezone offset configurations).

---

### 📁 Filter Panel (Left Navigation)
A collapsible sidebar designed to filter and isolate scanned directory assets:
* **Search input field**: Live-filters files dynamically as you type.
* **Age slider**: Filters files based on their last-modified age in minutes.
* **Hierarchy Folder Tree view**: Standard directory folder outline matching the disk structure.
* **Flat View list**: Replaces directory grouping with a unified, alphabetical flat list of all project files.
* **Toggle Buttons**:
  * *Files*: Hide or show scene backdrops and notes.
  * *Flat*: Switches the model from folder tree hierarchy to flat listing.
  * *V-Stack*: Collapses version folders to show only the highest parsed version.
  * *Sequences*: Identifies and collapses continuous image sequences into a single representative sequence asset with start/end frames noted.
* **📂 Filter Tree Context Menu**:
  * *Reveal in Filesystem*: Opens Windows Explorer at the location of the selected file or folder and highlights it.
  * *OS Open*: Opens the file or folder using default system handler configurations (e.g. standard picture viewer).
  * *Rename to Label*: Updates the physical file on disk to match the assigned label string from the spreadsheet.
  * *Edit / Delete* (Scene Items): Allows renaming or deleting backdrop labels and text note content selected in the scene layout tree.

---

### 🖼️ Thumbnail View (Graphics Scene)
A high-performance visual canvas displaying asset thumbnails, annotation backdrops, and video overlays.

#### 🎛️ Header Controls
* **Cols Spinner**: Directly sets the number of columns to arrange thumbnails into.
* **Show Text Checkbox**: Toggles the display of filename and metadata text labels underneath thumbnail graphics cards.
* **Text Slider**: Scales the font size of metadata labels inside the view.
* **Thumb Size Slider**: Scales the bounding box size of the thumbnail cards.
* **Player Mode Toggle Button**: Cycles player states:
  * *Player: Stop*: Stops and disposes of all video players.
  * *Player: Selected*: Playback is restricted to the single active highlighted video card.
  * *Player: All*: Spawns separate parallel overlays, playing every visible video in the view.
* **Filter Dropdown**: Cycles view sorting and filter scopes.

#### 🔍 Framing Actions
* **Double-Click**: Pans and zooms to frame the selected item in the viewport.
* **Frame Selection (Shortcut: `F`)**: Fits only selected thumbnails within the active viewport view.
* **Frame All (Shortcut: `A`)**: Pans and zooms out to fit the entire scene boundary including all text notes and backdrops.

#### 📂 Thumbnail Context Menu
* **Add Text Note**: Inserts a new text note box at the current mouse coordinates.
* **Add Backdrop**: Inserts a new resizable colored backdrop panel.
* **Edit Backdrop** (when triggered over backdrop): Modifies name labels and background HSL colors.
* **Enable/Disable Selected**: Toggles items between active and "do not convert" (grayed out) states.
* **Sequence Rename...**: Opens the batch renaming window.
* **Label Modifiers**:
  * *Reset Label*: Reverts custom label strings back to scanned defaults.
  * *Add Prefix / Add Suffix*: Prepends or appends character strings to selected item labels.
  * *Search and Replace*: Standard search-and-replace queries across selected item labels.
  * *Trim Actions (Length / Right / Left)*: Strips or clamps labels to specific text spans.
* **Arrange**: Reflows all thumbnails cleanly into rows and columns, ignoring manual drag-movements.
* **Open Review Video in System Player**: Launches the local transcode MP4 review in the default OS player.

---

### 📊 Spreadsheet Panel (Table Sheet)
A structured spreadsheet layout detailing metadata, conversion tasks, and validation results.

#### 🎛️ Header Controls
* **Selected Only Button**: Filters the table rows to show only the highlighted rows.
* **Enabled Only Button**: Filters rows to show only active (non-disabled) items.
* **Version Check & Fix**: Validates versions against the AYON database and attempts automatic conflicts resolution.
* **Check Duplicities**: Scans spreadsheet records to highlight version collisions and name duplication conflicts.
* **Enable/Disable Selected**: Toggles rows between active and ignored (disabled) states.
* **CSV Button**: Toggles the layout into a raw CSV preview grid.
* **Comment Field & Button**: Mass-appends custom comments or pipeline notes to all selected items.
* **Row Height Slider**: Scales row spacing using a quadratic slider to size image thumbnails.

#### 📂 Header & Row Context Menus
* **Horizontal Header Context Menu**:
  * *Show All Columns*: Instantly restores visibility of all columns.
  * *Column List Toggles*: Individually toggles the hidden state of each spreadsheet column (File Path, Label, Variant, Product, Category, Version, Codec, etc.).
* **Spreadsheet Row Context Menu**: Matches the Thumbnail view label editing tools (Reset, Prefix, Suffix, Search & Replace, Trim lengths, and Enable/Disable toggles).

---

### 🤖 AYON Panel (Auto-Assign Sidebar)
Manages integrations, validation queries, and metadata mapping tasks.

#### 📦 Products Panel
* Renders a nested hierarchy list detailing all existing **Products** under the active AYON task.
* **Columns**: Displays *Product Name*, *Type*, and the *Last Version* found in the database.
* **Filter Types Combo**: A checkable dropdown used to selectively filter out product items by category (e.g. `render`, `plate`, `model`, `comp`).
* **Double-Click Product**: Prompts to match and auto-assign the selected variant and project context to your local spreadsheet line.

#### 🎞️ Representations Panel
* Double-clicking an existing product expands this sub-grid showing target published files inside the AYON database.
* **Columns**: Displays *Name* (extension, e.g. `exr`, `mp4`), *Version*, *Status*, and *Path* location on network shares.
* **Representations Context Menu**:
  * *OS Open / Copy Path*: Launches or copies the exact target representational path on system mount directories.

#### 📂 Task Tree Context Menu
* **Assign path to selection**: Binds the highlighted AYON database task tree hierarchy to the current spreadsheet rows selection.
* **Unassign path / Select assigned items**: Dissolves bindings or selects corresponding spreadsheet rows.

---

### ⚙️ 2. Conversion Queue Dialog Reference
A dedicated processing window used to transcode files locally and verify review statuses on disk:
* **Table View**: Lists active transcode items, input files, output targets, and completion progress bars.
* **Convert Thumbnails Button**: Starts local thumbnail generation for all items.
* **Convert Reviews Button**: Starts ffmpeg review movie conversions.
* **Check Existing Button**: Scans local directory storage via expected paths, updating matches to green `done` review statuses and automatically refreshing the Filter Panel and spreadsheet indicators.
* **Clear Completed**: Clears completed items from the queue view.

---

### 📥 3. Bottom Export CSV
Located at the bottom right of the primary workspace layout:
* **Export CSV Button**: Compiles all active rows and formats their settings (delimiters, columns) using parameters configured in preferences, saving a raw spreadsheet log document.

---

## 🎨 4. Visual Orienting Cues & Color Codings

IngestDesktop uses high-contrast visual cues to help users orient themselves quickly:

### 🔲 Border Color Coding (Thumbnail Cards)
* **Light Gray (`#333333`)**: Standard idle card border.
* **Vibrant Yellow/Gold (`#ffaa00`)**: Indicates the item is currently selected, matched by filter queries, or playing reviews.
* **Green (`#4caf50`)**: Indicates the item has successfully passed Ingest Check validation with zero errors.

### 📐 Ingest Status Corner Indicators
Each thumbnail card features a colored corner badge representing its validation check status:
* **Green Check (`OK`)**: File is fully structured, hashed, and has passed all collision validations.
* **Red Cross (`Failed`)**: File contains layout, checksum, or version stack conflicts.
* **Gray Mark (`Unknown`)**: Pre-check status. Awaiting validation queries.

### 🔴 Disabled & Excluded Item Indicators
* **Red-Tinted Text / Labels**: Applied to rows, tree items, and thumbnail labels when set to `"do not convert"` or explicitly disabled from processing.
* **Semi-Transparent Cards**: Excluded thumbnail images are rendered with reduced opacity, making it easy to identify assets omitted from local review transcodes or Deadline submissions.

---

## ⚙️ 5. Preferences Dialog Configuration Reference

### 📁 General Tab
* **Default Scan Folder**: Default folder loaded on application launch.
* **Presets Folder**: Holds auto-assign `.json` configuration templates.
* **Ingest Log Folder**: Directory where text-based validation results are stored.
* **Per Project Logging**: Creates sub-directories matching project names for clean logs organization.
* **Age Calculation Source**: Toggles between checking the file's *Modification Date* or *Creation Date*.
* **Sequence Detection**: Enables grouping of frame lists into sequence summaries.
* **Version Collision Settings**:
  * *fail on existing*: Aborts publishes if the version exists.
  * *set to lowest available*: Finds the first unused version slot.
* **Create Ingest Report Checkbox**: Enables automated compilation of A4 Landscape PDF reports when validation finishes.
* **Timezone Offset A input**: Defines the UTC offset tag for the local capture environment.
* **Timezone Offset B input**: Defines the client's UTC offset, automatically generating shifted client-centric date strings on exports.

### 🤖 AYON Tab
* **AYON Server URL**: Target AYON database URL endpoint.
* **AYON Console Path**: Location of `ayon_console.exe` or `ayon.exe` on disk.
* **Product Name Template**: Text pattern (e.g. `{label}`) representing output naming.
* **Product Name camelCase**: Normalizes output folder targets.
* **Project Name**: Target project name scope.
* **CSV Ingest Folder & Task**: Target pipeline folder path designations.
* **Ingested Version Status**: Set the default status string for processed versions (e.g. `Pending Review`).
* **Set Statuses**: Toggles setting statuses for products/tasks after check queries.

### 🧩 Auto-Assign Tab
* **Version Regex / Folder Regex / Task Regex**: Pattern inputs representing metadata extraction schemas.
* **Fixed Task Name**: Forces a constant string overlay (e.g., `comp`) ignoring folder regex matches.
* **Sequence Regex / Episode Regex**: Extracts sequence and episode strings.
* **Assign Leaf Match**: Resolves conflicts by picking the first directory leaf directory match.

### 📊 CSV Tab
* **CSV Delimiter / Quote Character**: Delimiter config parameters.
* **CSV Columns Header list**: Multi-line plain text area defining CSV column headers and corresponding string tokens.

### 🎬 Conversions Tab
* **Run Thumb / Review after scan**: Automates transcode actions immediately upon scanner finishes.
* **Skip Existing**: Skips files with previously generated target reviews/thumbnails.
* **Sequence Thumbnail Frame**: Pick which frame (First/Second/Middle) of a sequence represents the thumbnail.
* **High-Res Size Limit**: Cap resolution dimensions for thumbs.
* **Thumbnail Location & Path**: Destination configuration (same folder, relative folder, custom path).
* **Command Templates**: Custom FFmpeg execution commands for stills, videos, and sequences.
* **Tool Paths**: Absolute targets for FFMpeg, FFProbe, OIIOTool, VFX Transcode, and OCIO configuration files.

### 📋 Clipboard Tab
* **Default Temp Root**: Directory folder where pasted clipboard visuals are saved.
* **Folder Template / File Prefix / Counter Padding**: Configures filenames for pasted items.

### 🎨 GUI Tab
* **Default Grid Columns / Text Size / Thumb Size**: Configures grid scale parameters.
* **Allowed Label Characters**: Regex restricting inline label renaming characters.
* **Inline Video Player toggle**: Disable default Qt loops player to use OS default mappings.

### 🏷️ Stills / Sequences / Videos / Other Tabs
* Edit and register system-wide presets mapping file extension structures to default transcode parameters.
