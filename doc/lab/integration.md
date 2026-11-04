# Integration: lab code, upstream merges, tests

## Repository layout

- **Remotes** (in the lab checkout): `origin` = `git@github.com:nrsc/acq4U.git` (the lab repo, branch `main`);
  `upstream` = `https://github.com/acq4/acq4.git` (official acq4). The local branch `upstream-main` tracks
  official acq4 and is useful for diffing.
- **Base:** official acq4 0.10.41 (`c6c09ac55`). `git diff upstream-main main` shows every lab change.
- **Environment:** conda env `acq4U`, Python 3.12, `pip install -e ".[micromanager,scientifica,dev]" pywin32`.

## What the lab changed

| File | Change | Why |
|---|---|---|
| `acq4/util/imaging/imaging_ctrl.py`, `imaging_template.ui` | `addPinnedFrame(im, frame, fileHandle)` sets z **after** `ViewBox.addItem`; pins keep their source `Frame` and file; **Export Mosaic** button (`exportMosaic`, `defaultMosaicFileName`) | `ViewBox.addItem` raises z below -100 to -99, so pins drew over live video after ~98 pins. Mosaic export references source files instead of copying them. |
| `acq4/modules/Camera/CameraWindow.py` | drop filter on the view (`eventFilter`, `pinFiles`); module-level `framesWithSources(handle)`; `displayPinnedFrame(frame, fileHandle)` | Drag images or folders from the Data Manager onto the camera view to pin them. |
| `acq4/util/DirTreeWidget/DirTreeWidget.py` | `mimeData()` adds file URLs | Lets other widgets accept drags from the Data Manager tree. Drops must be accepted as **CopyAction**; a MoveAction removes the dragged tree items. |
| `acq4/modules/DataManager/metadata_export.py` (new) | Notebook row builder: `TAB_COLUMNS`, `exportColumns`, `REQUIRED_FIELDS`, `cellRow`, `notebookTab`, `missingFields`, `autoCellID`, `realName`, `rowsToCsv/Tsv` | Joint-notebook export. Pure Python, no Qt. |
| `acq4/modules/DataManager/metadata_dialog.py` (new) | `MissingMetadataDialog` | Prompts for empty required fields, using the Data Manager's own field widgets (`FileInfoView.fieldTypes`). |
| `acq4/modules/DataManager/DataManagerModule.py`, `DataManagerTemplate.ui` | **Export Metadata** button; `completeMetadata`; new cells named `.01`, `.02`… in the nearest Slice (`_nextCellName`) with `ID` autofilled; `updateCellID` on rename; `loadPinnedImages` keeps source files | Lab naming convention and notebook workflow. |
| `acq4/util/DataManager/common.py`, `__init__.py`, `dot_index.py` | `casepath()`; handles are cached by `abspath()` (normalized key) but store `casepath()` (on-disk capitalization); `incrementFileName` matches case-insensitively; `_parentMoved` compares normalized prefixes | Upstream stored the lowercased path in every handle on Windows, so the Data Manager showed lowercase names and `mkdir` created lowercase folders. |
| `acq4/util/DataManager/dot_index.py` | `rename`/`move` run inside `_logFileReleased(path)`; `rename` drops the parent index entry only after success | Windows can't rename a folder holding the open `log.json`; upstream lost the index entry on a failed rename. |
| `acq4/Manager.py` | `logFileReleased(path)` context manager | Closes the log during a rename/move of its folder, then reopens it at the new path. |
| `acq4/logging_config.py` | `setup_logging` closes replaced FileHandlers; `close_log_file()` | Upstream leaked log file handles, so every folder that ever held the log stayed locked. |
| `acq4/devices/Scientifica/scientifica.py` | default `userSpeed` = controller's own top speed | Upstream defaulted to the stage's `fastSpeed` (1 mm/s) and wrote it to the controller permanently, capping the rotary controller. |
| `acq4/modules/MosaicEditor/MosaicEditor.py`, `acq4/util/Canvas/items/CellCanvasItem.py` | Save takes `[0]` of `getSaveFileName`; folder loading reads `dirType` from the folder's `.index` and also loads `.tif/.png/.jpg` images | Upstream: Save failed with `'tuple' object has no attribute 'endswith'`; loading a folder failed on the leftover, always-None `dataModel`, and found only `.ma` files. |
| `config/folderTypes.cfg` | shared folder types with lab dropdowns | One definition for every rig (see [personalization.md](personalization.md)). |
| `tools/lab_*.py`, `LAB_INSTALL.md`, `doc/lab/` | tests, config checker, docs | |

## Things that behave differently on Windows

- **Path case.** `common.abspath()` lowercases on Windows (`os.path.normcase`) and is the cache key and the way
  to compare paths. Handle paths (`handle.name()`, `shortName()`) keep their on-disk capitalization through
  `common.casepath()` (lab change). Compare paths with `abspath()`, never with `==` on `name()` strings.
  Folders created by upstream acq4U before this fix are lowercase on disk (e.g. `donor_000`) and stay that
  way until renamed. `metadata_export.realName(handle)` reads a name's on-disk case and is kept as a safeguard.
- **Renaming in code vs in the tree.** Calling `handle.rename()` directly while the Data Manager shows that
  item gets reverted: the tree item still has the old text, and the next font update fires `itemChangedEvent`,
  which renames it back. Rename through the tree (`tree.item(handle).setText(0, newName)`) in tests.

## Merging a new upstream acq4 release

```powershell
git fetch upstream
git merge upstream/main            # resolve conflicts in the files listed above
pip install -e ".[micromanager,scientifica]" pywin32
python -u tools\lab_featuretest.py <scratch dir> <repo> <acq4_data dir>
python -u tools\lab_renametest.py <scratch dir> <repo>
python tools\lab_check_config.py
```

- Re-check the Windows behaviors above; upstream may have fixed or changed them.
- If upstream bumps pymmcore, its 4th version number (device interface) must match the installed
  Micro-Manager (`CMMCore().getAPIVersionInfo()`). See [startup.md](startup.md#micro-manager-cameras).
- Upstream module class names can change (e.g. the Mosaic Editor is `MosaicEditorModule`).

## Tests

All three tools run without hardware. They set `QT_QPA_PLATFORM=offscreen`.

| Tool | What it does |
|---|---|
| `tools/lab_featuretest.py <scratch> <repo> <acq4_data>` | Starts the real Manager on the mock config with the shared `folderTypes.cfg`, copies `.index` files and 5 mosaic images from real data into scratch, and checks cell naming, metadata export (all three layouts), pin z-order, drag-and-drop, Load pinned images, mosaic export + Mosaic Editor reload, and the Mosaic Editor's own Save and folder loading. 21 checks. Needs `Human\H26.03.302` and `Macaque\Nemestrina\QN26.26.038` in the data folder. |
| `tools/lab_renametest.py <scratch> <repo>` | Creates Day/Donor/Slice folders and renames them through the Data Manager tree while they hold the log; checks the log follows and no index entry is lost. 8 checks. |
| `tools/lab_check_config.py [default.cfg]` | Checks a machine's config: device drivers, module classes, shared folder types, storage folder, Micro-Manager adapter compatibility (no device is initialized). |

Writing new headless tests:

- Start the Manager with `Manager.makeArgParser().parse_args(["-c", cfg, "-n", "-b", dataDir, "-m", "Data Manager"])`
  and `Manager.runFromCommandLine(args)`. With `-n` (no Manager window) at least one `-m` module is required.
- Pump the Qt event loop (`app.processEvents()`) after UI actions; many updates are signal-driven.
- Run with `python -u` when the script ends in `os._exit()`; otherwise buffered output is lost when piped.
- Copy `.index` files with `glob(..., recursive=True, include_hidden=True)`: cell and slice folders start
  with a dot and plain `glob` skips them.
- Load built-in module classes with `acq4.modules.importBuiltinClasses()` before `getModuleClass()`.
