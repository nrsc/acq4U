# Personalization: what to change, and where

## Config layers

| Layer | Location | Shared? | Examples |
|---|---|---|---|
| Lab-wide | `config/folderTypes.cfg` (tracked) | every rig, through git | folder types, metadata fields, dropdown presets |
| Lab-wide (code) | `acq4/modules/DataManager/metadata_export.py` | every rig, through git | notebook columns, required fields, field-to-column mapping |
| Per machine | `config/default.cfg`, `devices.cfg`, `devices/`, `modules/`, `protocols/` (untracked) | never | hardware, camera, calibrations, storage folder, window layouts, stage positions |

Lab-wide changes are edited in the repo, committed, pushed, and pulled on each rig (then restart acq4).
Per-machine changes are made on that machine only.

**Keep folder types in one place.** Edits made in an older acq4 install's `folderTypes.cfg` don't reach acq4U.
Before changing the shared file, compare it with any older install still in use and merge the differences
(`git status` shows local edits to `config/folderTypes.cfg` that were never shared).

## Folder types (`config/folderTypes.cfg`)

Each folder type (Day, Donor, Slice, Cell, Mosaic, …) has a `name` (folder-name pattern, passed to
`time.strftime`), optional `experimentalUnit: True` (the folder gets its own `log.json`), and an `info:` list of
metadata fields:

```
Slice:
    name: "slice"
    experimentalUnit: True
    info:
        User: "list", ["ScottS", "Brian", ...]   # editable dropdown, starts blank
        slice_type: "list", ["acute", "culture"]
        DIV: "string"                              # one-line text
        notes: "text", 4                           # multi-line text, 4 lines tall
```

Field types (`FileInfoView.fieldTypes`): `string`, `text` (with a line count), `list` (editable dropdown;
values outside the list still work), `bool`. Field names are written as-is into `.index` files, so renaming a
field orphans existing data: add the new name and map both in the export instead.

Conventions used by the notebook export (`metadata_export.cellRow`):

- Drug lists use `;` in acq4 (`Ket;WAY635`); wash sweeps pair by position (`wash_sweep: '55;76'`).
  The export writes `Ket@Sw55+WAY635@Sw76`.
- Slice `Brain_region` is the specific area (ITG); `Cortical_area` is the broader one (TCx).
- The cell's class goes in `Operator_call` (`IN`, `L5_ET`, `L2/3_IT`); `Cell_type` and `Layer_estimate` fall back
  to it when blank.

## Notebook export (`metadata_export.py`)

| To change | Edit |
|---|---|
| a notebook tab's columns or order | `TAB_COLUMNS` (copy the sheet's header row exactly) |
| how far rows extend | `exportColumns(tab)` (currently through `bath_drug`; culture through `DIV`) |
| which empty fields prompt the user | `REQUIRED_FIELDS`: `(dirType, field, condition)` |
| where a column's value comes from | `cellRow()` |
| tab selection | `notebookTab()` (human cells use Slice `slice_type`; others NHP) |
| species from donor prefix | `_SPECIES_BY_PREFIX` |

To refresh a tab's header, download it as CSV with
`https://docs.google.com/spreadsheets/d/<sheet id>/export?format=csv&gid=<tab gid>` and compare the first row
with `TAB_COLUMNS[tab]`. Exports go to the clipboard (tab-separated, pastes into cells) and to
`<storageDir>/.metadata/<cell or slice>.csv`.

## Cell naming

New cells created inside a Slice are named `.01`, `.02`… (highest existing number + 1) and get
`ID = <donor><slice><cell>` with on-disk capitalization (`DataManagerModule._nextCellName`,
`metadata_export.autoCellID`). Renaming a cell in the tree updates the ID only if it was empty or still the
autofilled value.

## Per-machine settings

### Micro-Manager cameras

Set `path:` in the camera's `devices.cfg` section to a Micro-Manager install matching pymmcore's device
interface. See [startup.md](startup.md#micro-manager-cameras).

### Scientifica stages

- With no `userSpeed:` in the device config, acq4U uses the controller's own stored top speed (lab change).
  Setting `userSpeed:` (m/s) makes acq4U write that value to the controller at startup and after every
  programmed move. The controller stores it permanently.
- `params:` values (e.g. `maxSpeed`, `joySlowScale`, `joyFastScale`, `axisScale`) are also written to the
  controller at startup and persist. Leave them commented out unless you intend to change the hardware.
- `scale:` converts controller positions (already in µm) to metres. Use `1e-6` per axis, with the sign
  choosing direction. Some older configs have `1e-7` for Z, which makes Z distances 10× too small.

### Window layouts and saved positions

Window geometry is saved in `config/modules/*_ui.cfg` on close; stage positions in
`config/devices/<device>_config/`. These are per machine and are not shared.
