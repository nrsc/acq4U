# Error logging and known issues

## Where log output goes

| Output | Location | Contents |
|---|---|---|
| Console | terminal that ran `python -m acq4` | `WARNING` and above by default (`--log-level DEBUG` for everything) |
| Log window | **Log** button in any acq4 window's status bar; **Show Log…** in the error dialog | all records for this session |
| Error dialog | "ACQ4 Error" popup | each `ERROR` record; **Show next error** steps through a burst |
| `temp_log.json` | the folder acq4 was launched from | records before any log folder is set; merged into the first `log.json`, then deleted |
| `log.json` | the current experimental-unit folder (Day, Donor or Slice) in `acq4_data` | all records (`DEBUG` and up) while that folder is the log folder |
| `crash.log` | the folder acq4 was launched from | Qt-level errors with stack traces |

The log folder follows the current directory: selecting or creating a Day, Donor or Slice makes it the log
folder. When that folder is renamed or moved, the log file follows it (lab fix in `Manager.logFileReleased`).

## Reading `log.json`

One JSON record per line, written by python-json-logger. Useful fields: `created` (Unix time), `name`
(logger, e.g. `acq4.util.DirTreeWidget.DirTreeWidget`), `level` (10 debug … 40 error) and `levelname`,
`message`, `pathname`, `lineno`, `threadName`, `exc_info` (traceback lines).

```python
import json, datetime
for line in open(r"C:\Users\<you>\acq4_data\...\log.json", encoding="utf-8"):
    rec = json.loads(line)
    if rec.get("level", 0) >= 40:
        print(datetime.datetime.fromtimestamp(rec["created"]), rec["name"], rec["message"])
        print("".join(rec.get("exc_info") or []))
```

## Reporting or triaging an error

Collect, in this order:

1. The error dialog text or the matching `log.json` record (with `exc_info`), plus a few records before it.
2. What the user was doing (which window, which folder, which button).
3. `python tools\lab_check_config.py` output for config, driver or camera problems.
4. Whether another acq4 or LinLab was running (`Get-Process python`, `Get-Process LinLab*`).

Fix the cause in code or config, add a check to `tools/lab_*test.py` when the bug can be reproduced without
hardware, and add the symptom to the table below.

## Known issues

| Symptom | Cause | Status |
|---|---|---|
| `PermissionError: [WinError 5] Access is denied` renaming a new Donor/Slice | the folder held the open `log.json`; old log files were never closed | fixed (lab): log released during rename; handlers closed. Test: `lab_renametest.py` |
| A failed rename removes the folder from its parent's `.index` | upstream dropped the entry before attempting the rename | fixed (lab). To repair old damage, with acq4 closed: `DirHandle(parent).indexFile(name, info={'__timestamp__': child.info()['__timestamp__']})` |
| Pinned frames cover the live image after many pins | z set before `ViewBox.addItem` | fixed (lab) |
| Rotary controller lost fast mode; persists after power cycle | acq4 wrote a 1 mm/s top speed to the Scientifica controller | fixed (lab default); controllers changed earlier must be reset (`setParam('maxSpeed', …)`, with approval) |
| Folder names show lowercase in the Data Manager; new folders created lowercase (`donor_000`) | upstream stored normcased (lowercase) paths in every handle on Windows | fixed (lab): handles keep on-disk case (`common.casepath`). Folders created lowercase before the fix stay lowercase until renamed. Test: `lab_renametest.py` |
| Camera adapter fails to load | pymmcore / Micro-Manager device interface mismatch | see [startup.md](startup.md#micro-manager-cameras) |
| acq4 keeps running after its window closes | "ACQ4 Error" dialog still open | close the dialog |
| LinLab can't see a controller | acq4 holds its COM port | close acq4 |
