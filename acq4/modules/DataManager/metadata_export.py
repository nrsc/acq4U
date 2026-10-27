"""Build joint-notebook rows from the acq4 .index metadata of Cell folders.

Each row follows the column order of one joint-notebook tab (NHP, Human_acute or Human_culture;
Google Sheets), so that a row can be pasted directly into that tab. Columns that cannot be determined from
acq4 metadata (LIMS fields, reconstruction, layer estimates, ...) are left empty.
"""
import csv
import io
import os
import re
import time
from collections import OrderedDict

# Column order of each joint-notebook tab (header rows as of 2026-10-02). Tabs differ in order
# and content, so a row must be built for the tab it will be pasted into.
TAB_COLUMNS = OrderedDict([
    ("NHP", [
        "Donor", "Species", "Date", "User", "Slice_ID", "cell_name", "sample_id", "file_path",
        "features_extracted", "feature_extraction_notes", "LIMS_20x", "Fill_notes", "LIMS_63x",
        "Reconstruction", "Brain_Region", "Depth_from_pia", "LIMS_depth", "Cell_type",
        "Layer_estimate", "LIMS_layer", "Operator_call", "Slice_location", "Comments", "Experiment",
        "Fast_blockers", "puff_drug", "wash_drug", "bath_drug", "drug", "Drug_concentration",
        "Drug_date", "protocols", "Virus", "Reporter_positive", "Notes",
    ]),
    ("Human_acute", [
        "Donor", "Date", "User", "Slice_ID", "cell_name", "sample_id", "file_path",
        "features_extracted", "feature_extraction_notes", "LIMS_20x", "Fill_notes", "LIMS_63x",
        "Reconstruction", "Brain_Region", "Depth_from_pia", "LIMS_depth", "Cell_type",
        "Layer_estimate", "LIMS_layer", "Operator_call", "Slice_location", "Comments", "Experiment",
        "Fast_blockers", "puff_drug", "wash_drug", "bath_drug", "drug", "Drug_date",
        "Drug_concentration", "protocols", "Chirp_sweeps", "FI_sweeps", "VI_sweeps",
        "s5HT-bl_sweeps", "s5HT-sti_sweeps", "r5HT-bl_sweeps", "r5HT-sti_sweeps",
    ]),
    ("Human_culture", [
        "Donor", "Date", "User", "Slice_ID", "cell_name", "sample_id", "file_path",
        "features_extracted", "feature_extraction_notes", "LIMS_20x", "LIMS_63x", "Reconstruction",
        "Brain_Region", "Depth_from_pia", "LIMS_depth", "Cell_type", "Layer_estimate", "LIMS_layer",
        "Operator_call", "Slice_location", "Comments", "Experiment", "Fast_blockers", "puff_drug",
        "wash_drug", "bath_drug", "drug", "Drug_date", "Drug_concentration", "Virus",
        "Reporter_positive", "DIV", "DPI", "Chirp_sweeps", "FI_sweeps", "VI_sweeps",
        "s5HT-bl_sweeps", "s5HT-sti_sweeps", "r5HT-bl_sweeps", "r5HT-sti_sweeps", "topLeaf_label",
        "seurat_cluster_label", "seurat_prediction_score_label", "Norm_Marker_Sum.0.4_label",
        "topLeafValue", "subclass_label", "cluster_label", "res_index",
    ]),
])

# every column of every tab, in first-seen order
ALL_COLUMNS = list(OrderedDict((c, None) for cols in TAB_COLUMNS.values() for c in cols))


def exportColumns(tab):
    """Columns written for *tab*: everything through bath_drug (later columns are legacy or filled
    downstream), extended on the culture tab through Virus, Reporter_positive and DIV."""
    cols = TAB_COLUMNS[tab]
    last = "DIV" if tab == "Human_culture" else "bath_drug"
    return cols[:cols.index(last) + 1]


# Fields that are routinely filled in the notebook and must be complete before exporting:
# (dirType, field, condition(sliceInfo, cellInfo) -> required?). Edit this list to change the prompt.
REQUIRED_FIELDS = [
    ("Slice", "User", None),
    ("Slice", "slice_type", None),
    ("Slice", "Brain_region", None),
    ("Slice", "blockers", None),
    ("Slice", "DIV", lambda slc, cell: _clean(slc.get("slice_type")).lower() == "culture"),
    ("Cell", "depth from pia", None),
    ("Cell", "Operator_call", None),
    # interneuron calls (IN, SST, ...) carry no layer, so ask for it explicitly
    ("Cell", "Layer_estimate", lambda slc, cell: not _callLayer(_clean(cell.get("Operator_call")))),
]

# Macaque species by donor-name prefix, written the way the notebook spells them.
_SPECIES_BY_PREFIX = OrderedDict([
    ("QN", "M.nemestrina"),
    ("QM", "M.mulatta"),
    ("QF", "M.fascicularis"),
])

# acq4 Cell "type" values -> notebook Cell_type abbreviations
_CELL_TYPES = {"pyramidal": "PN", "inhibitory": "IN"}

# Operator_call patterns -> Cell_type, used when "type" was not entered (checked in order)
_CALL_CELL_TYPES = [
    (re.compile(r"\b(IN|INT|SST|PVALB|PV|VIP|LAMP5|SNCG|CHANDELIER)\b", re.I), "IN"),
    (re.compile(r"MSN", re.I), "MSN"),
    (re.compile(r"NUDAP", re.I), "GC"),
    (re.compile(r"(IT|ET|NP|CT|L6b)\b|L3c", re.I), "PN"),
]

# leading layer in an Operator_call: L5_ET -> L5, L2/3_IT or L23 IT -> L2/3, L3c -> L3
_CALL_LAYER = re.compile(r"^\s*L(1|2/3|23|2|3|4/5|4|5/6|5|6)", re.I)


def _callCellType(call):
    for pattern, cellType in _CALL_CELL_TYPES:
        if pattern.search(call):
            return cellType
    return ""


def _callLayer(call):
    m = _CALL_LAYER.match(call)
    if m is None:
        return ""
    return "L" + {"23": "2/3"}.get(m.group(1), m.group(1))

# acq4 Slice "blockers" presets -> notebook spelling
_BLOCKERS = {"Ptx/Ka": "Ptx/KA"}

# values that mean "nothing entered"
_EMPTY = {"", "none", "unknown", "n/a", "na"}


def _splitList(value):
    return [v.strip() for v in value.split(";") if v.strip()]


def _joinDrugs(value):
    """acq4 drug lists are ';'-separated; the notebook joins them with '+' (Ket;WAY -> Ket+WAY)."""
    return "+".join(_splitList(value))


def _washDrugs(drugs, sweeps):
    """Pair wash drugs with their wash-in sweeps: ('Ket;WAY', '55;76') -> 'Ket@Sw55+WAY@Sw76'."""
    drugs, sweeps = _splitList(drugs), _splitList(sweeps)
    out = []
    for i, drug in enumerate(drugs):
        if i < len(sweeps) and "@" not in drug:
            sweep = sweeps[i]
            drug += "@Sw" + sweep if sweep.isdigit() else "@" + sweep
        out.append(drug)
    return "+".join(out)


def _clean(value):
    if value is None:
        return ""
    value = " ".join(str(value).replace("\t", " ").split())  # flatten newlines/tabs for pasting
    return "" if value.lower() in _EMPTY else value


def _first(info, *keys):
    for key in keys:
        value = _clean(info.get(key))
        if value:
            return value
    return ""


def findCellDir(handle):
    """Return the Cell folder containing *handle* (or *handle* itself), or None."""
    while handle is not None and handle.isManaged():
        if handle.isDir() and handle.info().get("dirType") == "Cell":
            return handle
        handle = handle.parent()
    return None


def findCellDirs(handle):
    """Return the Cell folders to export for a selected file or folder.

    A selection inside a cell exports that cell; a selected Slice (or other folder)
    exports every Cell folder directly inside it.
    """
    cell = findCellDir(handle)
    if cell is not None:
        return [cell]
    if handle is None or not handle.isDir():
        return []
    cells = []
    for name in handle.ls(sortMode="alpha"):
        child = handle[name]
        if child.isDir() and child.isManaged() and child.info().get("dirType") == "Cell":
            cells.append(child)
    return cells


def _ancestor(handle, dirType):
    handle = handle.parent()
    while handle is not None and handle.isManaged():
        if handle.info().get("dirType") == dirType:
            return handle
        handle = handle.parent()
    return None


def realName(handle):
    """Return a file or folder name with its on-disk capitalization.

    acq4's file handles normalize paths with os.path.normcase, which lowercases them on Windows;
    donor IDs like QN26.26.038 must keep their case in IDs and exports.
    """
    name = handle.shortName()
    try:
        for entry in os.listdir(os.path.dirname(handle.name())):
            if entry.lower() == name.lower():
                return entry
    except OSError:
        pass
    return name


def autoCellID(cellDir, cellName=None):
    """Build a cell ID from the Donor, Slice and Cell folder names, e.g. QN26.26.038 + .19.07 + .01
    -> QN26.26.038.19.07.01. *cellName* overrides the cell folder's name (e.g. its name before a rename)."""
    parts = []
    donorDir = _ancestor(cellDir, "Donor")
    sliceDir = _ancestor(cellDir, "Slice")
    for name in (realName(donorDir) if donorDir is not None else None,
                 realName(sliceDir) if sliceDir is not None else None,
                 cellName if cellName is not None else realName(cellDir)):
        if name:
            parts.append(name if name.startswith(".") or not parts else "." + name)
    return "".join(parts)


def cellRow(cellDir):
    """Return an OrderedDict of notebook column -> value for one Cell folder."""
    cell = dict(cellDir.info())
    sliceDir = _ancestor(cellDir, "Slice")
    donorDir = _ancestor(cellDir, "Donor")
    slc = dict(sliceDir.info()) if sliceDir is not None else {}
    donor = dict(donorDir.info()) if donorDir is not None else {}

    row = OrderedDict((col, "") for col in ALL_COLUMNS)

    donorName = realName(donorDir) if donorDir is not None else ""
    row["Donor"] = donorName
    row["Slice_ID"] = donorName + (realName(sliceDir) if sliceDir is not None else "")
    row["cell_name"] = _first(cell, "ID") or autoCellID(cellDir)

    species = _first(donor, "species")
    if species.lower() in ("", "macaque"):
        species = next((sp for pre, sp in _SPECIES_BY_PREFIX.items() if donorName.startswith(pre)), species)
    row["Species"] = species
    # different people often patch different slices of one donor, so the slice's User wins
    row["User"] = _first(slc, "User") or _first(donor, "User")

    # recording date (when the cell folder was created), formatted like the notebook: 9/29/26
    stamp = cell.get("__timestamp__")
    if stamp is not None:
        t = time.localtime(stamp)
        row["Date"] = "%d/%d/%02d" % (t.tm_mon, t.tm_mday, t.tm_year % 100)

    row["sample_id"] = _first(cell, "JEM_code (sample_id)", "sample_id")
    # Slice "Brain_region" holds the specific area (e.g. ITG); "Cortical_area" the broader one (e.g. TCx)
    row["Brain_Region"] = _first(slc, "Brain_region", "Cortical_area", "location") or _first(donor, "region")
    row["Depth_from_pia"] = _first(cell, "depth from pia")
    call = _first(cell, "Operator_call")
    row["Operator_call"] = call
    cellType = _first(cell, "type")
    # fall back to the operator call (e.g. "IN", "SST", "L5_ET") when type/layer weren't entered
    row["Cell_type"] = _CELL_TYPES.get(cellType.lower(), cellType) or _callCellType(call)
    row["Layer_estimate"] = _first(cell, "Layer_estimate") or _callLayer(call)
    row["Slice_location"] = _first(cell, "location")
    row["Comments"] = _first(cell, "notes")
    row["Fast_blockers"] = _BLOCKERS.get(_first(slc, "blockers"), _first(slc, "blockers"))
    row["puff_drug"] = _joinDrugs(_first(cell, "puff_drug"))
    row["bath_drug"] = _joinDrugs(_first(cell, "bath_drug"))
    row["wash_drug"] = _washDrugs(_first(cell, "wash_drug"), _first(cell, "wash_sweep"))
    row["drug"] = _first(cell, "drug")
    row["Drug_concentration"] = _first(cell, "Drug_concentration")
    row["Virus"] = _first(slc, "viral labeling") or _first(cell, "viral labeling")
    row["Reporter_positive"] = _first(cell, "Reporter_positive")
    row["DIV"] = _first(slc, "DIV") or _first(donor, "DIV")
    row["DPI"] = _first(donor, "DPI")
    row["Chirp_sweeps"] = _first(cell, "chirp-sweeps")
    row["FI_sweeps"] = _first(cell, "FI-sweeps")
    row["VI_sweeps"] = _first(cell, "VI-sweeps")

    hasDrug = any(row[k] for k in ("puff_drug", "wash_drug", "bath_drug"))
    protocols = []
    if _first(cell, "FI-sweeps", "VI-sweeps", "chirp-sweeps"):
        protocols.append("basic props")
    if hasDrug:
        protocols.append("neuromodulation")
    row["protocols"] = ", ".join(protocols)
    if hasDrug:
        row["Experiment"] = "neuromodulation"
    elif row["sample_id"]:
        row["Experiment"] = "Patch-seq"

    return row


def isHuman(cellDir):
    donorDir = _ancestor(cellDir, "Donor")
    if donorDir is None:
        return False
    species = _first(dict(donorDir.info()), "species").lower()
    return species == "human" or (species == "" and re.match(r"H\d", realName(donorDir)) is not None)


def notebookTab(cellDir):
    """Return the notebook tab for a cell: NHP, or Human_acute / Human_culture from the Slice's
    slice_type. Returns None for a human cell whose slice_type is not set."""
    if not isHuman(cellDir):
        return "NHP"
    sliceDir = _ancestor(cellDir, "Slice")
    sliceType = _first(dict(sliceDir.info()), "slice_type").lower() if sliceDir is not None else ""
    return {"acute": "Human_acute", "culture": "Human_culture"}.get(sliceType)


def missingFields(cellDirs):
    """Return OrderedDict {folder handle: [required field names that are empty]} for the Slice and
    Cell folders of *cellDirs*, skipping folders with nothing missing."""
    missing = OrderedDict()
    for cellDir in cellDirs:
        sliceDir = _ancestor(cellDir, "Slice")
        slc = dict(sliceDir.info()) if sliceDir is not None else {}
        cell = dict(cellDir.info())
        for dirType, field, condition in REQUIRED_FIELDS:
            handle, info = (sliceDir, slc) if dirType == "Slice" else (cellDir, cell)
            if handle is None or _clean(info.get(field)):
                continue
            if condition is not None and not condition(slc, cell):
                continue
            fields = missing.setdefault(handle, [])
            if field not in fields:
                fields.append(field)
    return missing


def rowsToCsv(rows, tab="NHP"):
    """Return CSV text with one line per row, in *tab*'s export columns, and no header."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for row in rows:
        writer.writerow([row[c] for c in exportColumns(tab)])
    return buf.getvalue()


def rowsToTsv(rows, tab="NHP"):
    """Return tab-separated text in *tab*'s export columns (pastes into separate Google Sheets cells)."""
    return "\n".join("\t".join(row[c] for c in exportColumns(tab)) for row in rows)
