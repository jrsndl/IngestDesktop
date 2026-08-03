# IngestDesktop — The Reference 

This reference guide provides an exhaustive description of every interface panel, visual indicator, context menu, top control, and configuration tab available within **IngestDesktop**.

---

## 🎛️ Workspace Panels & Detailed Controls

### 🗺️ Top Bar (Navigation & Globals)
The control header at the very top of the application manages directory targets, scanning, and global timezones:
* **Source Folder input field**: Displays the currently scanned local or network directory path. Can be edited manually.
* **Select Source Folder button**: Opens a native system folder dialog to select a source directory.
* **Preset dropdown**: Allows to pick a preset - IngestDesktop configuration.
* **Load Preset button**: Allows to load selected preset - IngestDesktop configuration.
* **Clipboard Status indicator**: Displays state information when pasting clipboard imagery.
* **Preferences**: Displays preferences dialog.

---

### 📁 Filter Panel (Right Navigation)
A collapsible sidebar designed to filter and isolate scanned directory files:
* **Search input field**: Live-filters files dynamically as you type. Checkbox for fast disable
* **Age**: Filters files based on their created or last-modified age.
* **Hierarchy Folder Tree view**: Standard directory folder outline matching the disk structure.
* **Flat View list**: Replaces directory grouping with a unified, alphabetical flat list of all project files.
* **Toggle Buttons**:
  * *Files*: Hide or show scene backdrops and notes.
  * *Flat*: Switches the model from folder tree hierarchy to flat listing.
  * *Version Stack*: Collapses versioned files to show only the highest version.
  * *Sequences*: Identifies and collapses continuous image sequences into a single representative sequence asset with start/end frames noted.
  
* **📂 Filter Tree Context Menu**:
  * *Reveal in Filesystem*: Opens Windows Explorer at the location of the selected file or folder and highlights it.
  * *OS Open*: Opens the file or folder using default system handler configurations (e.g. standard picture viewer).
  * *Rename to Label*: Updates the physical file on disk to match the assigned label string from the spreadsheet.
  * *Edit / Delete* (Scene Items): Allows editing or deleting backdrop labels and text notes. Only works if *Files* are off.
  
* **🎨 Item Indicators**
  * Gray file name indicate file that is filtered out by name or age.
  * Red file name indicate file that is disabled: will not be published
  * The R icon indicate the file needs a Review. 
    * Orange R: Review not processed
    * Red R: Review processing failed
    * Green R: Review processing done
  * Checkmark or cross to indicate publish status
    * checkmark indicates successfult publish
    * cross indicates failed publish

---

### 🖼️ Thumbnail View (Graphics Scene)
A visual canvas displaying asset thumbnails, annotation backdrops, text notes and video overlays.

#### 🎛️ Controls
* **Frame All**: Sets the zoom and pan of the view so all the items are visible. Hotkey: Z. Doubleclicking empty space also works
* **Frame Selection**: Sets the zoom and pan of the view so selected items are filling the view. Hotkey: F. Doubleclicking empty single thumbnail also works when Player is stopped.
* **Cols Spinner**: Directly sets the number of columns to arrange thumbnails into. Only works when thumbnails are not user positioned.
* **Show Text Toggle**: Toggles the display of label underneath thumbnail.
* **Text Slider**: Scales the font size of labels.
* **Thumb Size Slider**: Scales the thumbnail cards.
* **Player Mode Toggle Button**: Cycles player states:
  * *Player: Stop*: Stops video players.
  * *Player: Selected*: Playback is restricted to the single active highlighted video card.
  * *Player: All*: Playing every visible video in the view.
* **Filter Dropdown**: Can temporarily hide disabled items.
* **Conversion Queue**: Shows spreadsheet with items that need Review.
* **Maximize**: Hides other panels for more space. Hotkey: spacebar.

### ⚙️ Conversion Queue Dialog
A dedicated processing window, shows review statuses. Hotkey: Ctrl+Q
Note that top menu convert options allow to force conversion even for items that have existing review or thumbnail file.
* **Convert Reviews Button**: Starts review conversions.
* **Convert Thumbnails Button**: Starts thumbnail conversions.
* **Check Existing Button**: Checks if Reviews exist on HDD. Useful when processing Reviews on farm.
* **Pause**: Pause the conversions
* **Restart**: Restart the conversions

#### 📂 Thumbnail Context Menu
* **Add Text Note**: Inserts a new text note box at the current mouse coordinates.
* **Add Backdrop**: Inserts a new resizable colored backdrop panel.
* **Edit Backdrop** (when triggered over backdrop): Modifies backdrop text and color options.
* **Enable/Disable Selected**: Toggles items between active and "do not convert" (grayed out) states. Hotkey: Ctrl+D
* **Sequence Rename...**: Opens the batch renaming window. This allows to quickly generate new labels, optionally with counter to make the labels unique. Hotkey: F2
* **Label Modifiers**:
  * *Reset Label*: Reverts custom label strings back to file name (excluding version and sequence number).
  * *Add Prefix / Add Suffix*: Prepends or appends character strings to selected item labels.
  * *Search and Replace*: Standard search-and-replace queries across selected item labels.
  * *Trim Actions (Length / Right / Left)*: Strips or clamps labels to specific text spans.
* **Arrange**: Reflows all selected thumbnails cleanly into rows and columns, with customisable gaps. Allows to sort the items by File name, Version, Label, File Size, Width, Height, Age and File extension.
* **Open Review Video in System Player**: Launches the transcoded review in the default OS player.

#### 🎨 Thumbnail Item Indicators
  * Red Rectangle indicates disabled item, green rectangle indicates enabled item
  * Bright Green Rectangle indicates item that has AYON folder and task assigned
  * Top left corner indicates publish status, green for suvccesfully published, red for failed publish.

---

### 📊 Spreadsheet Panel (Table Sheet)
A structured spreadsheet layout detailing metadata, conversion tasks, and validation results.

#### 🎛️ Header Controls
* **Selected Only Button**: Filters the table rows to show only the items highlighted in thumbnail or filter view.
* **Enabled Only Button**: Filters rows to show only active (non-disabled) items.
* **Version Check & Fix**: Validates versions against the AYON database and attempts automatic conflicts resolution (controlled by preferences).
* **Check Duplicities**: Scans spreadsheet records to highlight name collisions.
* **Enable/Disable Selected**: Toggles items between active and ignored (disabled) states.
* **CSV Button**: Switchhes the view to CSV preview mode. (controlled by preferences)
* **Add Comment**: Mass-appends custom comments or pipeline notes to all selected items. For CSV mode.
* **Row Height Slider**: Scales row spacing using a quadratic slider to size image thumbnails.

#### 📂 Header & Row Context Menus
* **Horizontal Header Context Menu**:
  * *Show All Columns*: Instantly restores visibility of all columns.
  * *Column List Toggles*: Individually toggles the hidden state of each spreadsheet column (File Path, Label, Variant, Product, Category, Version, Codec, etc.).

---

### 🤖 AYON Panel
Displays AYON folder and task hierarchy. Allows to assign items to AYON folders and tasks.

#### 📂 Controls
* **Project**: Displays AYON Project list.
* **Refresh**: Re-read the AYON Hierarchy.
* **Auto-Assign**: Assign the folders and tasks based on file names (controlled by preferences)
* **Search**: Allows to search for folder / task name, task type, task status or assignee
* **Assigned Only**: Only displays folders and tasks assigned to items
* **Show Thumbs**: Displays thumbnails for AYON folders (currently broken)
* **Clear All Assignments**: Remove AYON folder and task assignment from all items.

#### 📂 Task Tree Hierarchy - Context Menu
Note that only one folder & task can be selected in the AYON hierarchy
* **Assign path to selection**: Binds AYON folder and task assignment to item selection. Doubleclick also works.
* **Unassign path**: Dissolves bindings of folder and task assignment.
* **Select assigned items**: Select items assigned to the folder and task

#### 📦 Products Panel
* Renders a list detailing all existing **Products** under the active AYON task.
* Allows filtering by product type
* Displays last version

* **Double-Click Product**: This will assign folder and task, and also rename the label of selected item(s) to match the doubleclicked product.

#### 🎞️ Representations Panel
Displays representations of the last version selected in the Products Panel above

* **Collapse Checkbox**: When enabled (default), collapses representations to show only the highest version for each representation name.
* **Columns**: Displays *Name* (typically extension), *Version*, *Status*, and *File Path*
* **Double-Click Representation**: Executes the **OS Open** action to open the file with the default system application.
* **Representations Context Menu**:
  * *Reveal in Filesystem*: Opens File Explorer with the selected representation file
  * *OS Open*: Opens representation file with default app.

---

### 📥 Export CSV Button
Compiles all active rows and formats their settings (delimiters, columns) using parameters configured in preferences, saving a CSV spreadsheet that can be used for AYON Traypublisher

### 📥 Publish Ayon Local
Exports CSV file, runs AYON Traypublisher, checks the publish results. Can also write the Ingest Log, generate Ingest Report, and change status of versions and tasks.

### 📥 Process Reviews on Deadline
Gathers all files that require Review, and sends the processing to the farm.

---


## ⚙️ Preferences Dialog

### 📁 General Tab
* **Default Scan Folder**: Default folder loaded on application launch.
* **Presets Folder**: Path to store named configurations.
* **Ingest Log Folder**: Directory where Ingest Logs (CSV files) and optionally also Ingest Reports are stored.
* **Per Project Logging**: Creates sub-directories matching AYON project names for clean logs organization.
* **Age Calculation Source**: Toggles between checking the file's *Modification Date* or *Creation Date*.
* **Sequence Detection**: Enables grouping of frame lists into sequence summaries.
* **Version Collision Settings**:
  * *fail on existing*: Aborts publishes if the version exists. Marks versions orange in Spreadsheet.
  * *set to lowest available*: Finds the first unused version slot, and edits the version to it
* **Create Ingest Report Checkbox**: Enables automated compilation of A4 Landscape PDF reports when validation finishes.
* **Timezone Offset A input**: Defines the local UTC offset to be part of the Ingest Report
* **Timezone Offset B input**: Defines the client UTC offset to be part of the Ingest Report

### 🤖 AYON Tab
* **AYON Server URL**: Target AYON database URL endpoint.
* **AYON Console Path**: Location of `ayon_console.exe` or `ayon.exe` on disk.
* **Product Name Template**: Text pattern (e.g. `{label}`) representing output naming.
* **Product Name camelCase**: Normalizes output folder targets.
* **Project Name**: Default AYON project name.
* **CSV Ingest Folder & Task**: Folder and task for Traypublisher CSV. Make sure it exists in the project.
* **CSV Preset**: AYON now allows multiple CSV configurations, make sure presetr exists in project settings.
* **Ignore Validators** This option allows to ignore Traypublisher validators like frame range.
* **Ingest Check** Enables checking if published versions actually exist in AYON
* **Ingested Version Status**: Set the default status for published versions (e.g. `Pending Review`).
* **Play Sound on Finish**: Plays sound after AYON Publish finishes. (currently broken)
* **Set Product Status after Ingest Check**: set product status, same as version status
* **Set Task Status after Ingest Check**: set task status, same as version status
* **Set Neighbour Task Status after Ingest Check**: Finds the Neighbour task in the same folder, and sets it's status

### 🧩 Auto-Assign Tab
* **Version / Folder / Task / Sequence / Episode Regex**: Regular expressions for parsing the file name.
* **Fixed Task Name**: Forces a custom task name.
* **Sequence Regex / Episode Regex**: Extracts sequence and episode strings.
* **Assign first match if more than one leaf folder name matches**: Resolves conflicts by picking the first directory leaf directory match.
* **Assign first task if folder match is found, but task match is not**: Allows to assign whatever task folder has.

### 📊 CSV Tab
* **CSV Delimiter / Quote Character**: CSV format config.
* **CSV Columns Header list**: Multi-line plain text area defining CSV column headers and corresponding string tokens.

### 🎬 Conversions Tab
* **Run Thumbnail conversion after scan**: Automates transcode immediately upon scanner finishes.
* **Run Review conversion after scan**: Automates transcode immediately upon scanner finishes.
* **Skip Existing Thumbnails**: Skips conversions with existing thumbnails.
* **Skip Existing Reviews**: Skips conversions with existing reviews.
* **Sequence Thumbnail Frame**: Pick which frame (First/Second/Middle) of a sequence is picked for the thumbnail.
* **High-Res Thumbnail Size**: For thumbnail conversion. Token: {prefs_highres_thumb_size}
* **Thumbnail Location & Path**: Destination configuration (same folder, relative folder, custom path). Together with suffix and file formmat forms Token: {prefs_thumb_path}
* **Thumbnail Suffix**: Thubnail is named the same as the file, suffix can be used to make the thumbnail file unique.
* **Thumbnail File Format**: Thubnail extension. Token: {prefs_highres_thumb_size}
* **Command Templates**: Custom commands for generating thumbnails from categories (stills, videos, sequences). Typically uses FFmpeg. Can be overriden by category presets.
* **Tool Paths**: Absolute targets for FFMpeg, FFProbe, OIIOTool, VFX Transcode, and OCIO configuration files.
* **Timeout seconds** Conversion is cancelled if it takes longer than the timeout. Zero turns this feature off.

### 📋 Clipboard Tab
* **Default Temp Root**: Directory folder where pasted clipboard visuals are saved. Note that paths in IngestDesktop can use environment variables in curly brackets, prefixed by dollar sign *${envvarname}*
* **Folder Template / File Prefix / Counter Padding**: Configures filenames for images pasted from clipboard.

### 🎨 GUI Tab
* **Default Grid Columns / Text Size / Thumb Size**: Configures grid scale parameters.
* **Allowed Label Characters**: Regex restricting inline label renaming characters.
* **Inline Video Player toggle**: Disable default Qt player to use OS default mappings.

### 🏷️ Stills / Sequences / Videos / Other Tabs
IngestDesktop uses 5 file categories.
* Stills
* File Sequences
* Video Containers
* Other files
* Unknown / to be ignored files
Stills, Sequences, Videos and Other are defined by the list of allowed file extensions. File sequence with only one file is considered a still.

#### 🏷️ Category Presets
Stills, Sequences, Videos and Other categories can have one or more presets. Each preset has a filter (matching extension or part of the file name).
When file is assigned Category and Category Preset, it sets up maby values useful for the publishing or conversions.

### 🏷️ Secrets Tab
AYON API Key: for AYON authentication.
FTRACK Server, API Key and User: for FTRACK authentication. Sets the environment variables for AYON Traypublisher CSV publish.

### 🏷️ Deadline Tab
Values used for processing Reviews on the farm.