# Startup

## Launching

```powershell
conda activate acq4U
cd C:\Users\<you>\acq4U
python -m acq4
```

Launch from the repo folder. `temp_log.json` and `crash.log` are written to the **current working folder**
(see [error-logging.md](error-logging.md)), so launching from elsewhere scatters them.

Command-line options (`Manager.makeArgParser`):

| Option | Effect |
|---|---|
| `-c, --config FILE` | config file (default: first `default.cfg` found in `acq4U\config`, then `config\example`) |
| `-a, --config-name NAME` | apply a named entry from the config's `configurations:` section (repeatable) |
| `-m, --module NAME` | load a module defined in the config at startup (repeatable) |
| `-b, --base-dir DIR` / `-s, --storage-dir DIR` | override the Data Manager base / current directory |
| `-d, --disable DEVICE` / `-D, --disable-all` | skip configuring a device / all devices (useful for testing without hardware) |
| `-n, --no-manager` | don't open the Manager window (then at least one `-m` is required) |
| `-x, --exit-on-error` | stop at the first error during startup instead of continuing |
| `--log-level LEVEL` | console log level (default `WARNING`; use `DEBUG` to see everything in the terminal) |
| `--root-log-level LEVEL` | level for the `acq4` logger and the log file (default `DEBUG`) |

## Startup sequence

1. `acq4/__main__.py` creates the Qt app, installs a Qt message handler (writes `crash.log`), and calls
   `Manager.runFromCommandLine(args)`.
2. `acq4/Manager.py` starts logging to `temp_log.json` (in the working folder) until a log folder exists.
3. `Manager.readConfig()` reads `default.cfg` with pyqtgraph's config reader. Nested files are pulled in with
   `readConfigFile('devices.cfg')` and `readConfigFile('folderTypes.cfg')`, resolved relative to the config
   folder.
4. `Manager._loadConfig()` handles, in order: `imports:` (Python modules imported before anything else; the
   hook for extensions), `execFiles:`, then `devices:` (each device's driver is constructed and connects to
   hardware here), `modules:`, `misc:` (`folderTypes`, `storageDir`, compression), and the stylesheet.
5. The base directory (`storageDir` or `-b`) is set, then the Manager window and any `-m` modules open.
6. When a Day, Donor or Slice folder becomes current, it becomes the log folder: `temp_log.json` is merged
   into its `log.json` and deleted.

A device that fails to configure is logged and skipped; startup continues unless `-x` is given. Check the
log after startup for `Error configuring device <name>`.

## First-run checklist

- [ ] `python tools\lab_check_config.py` reports no `FAIL`.
- [ ] The camera shows live video; the stage and focus respond (including the rotary controller's fast mode).
- [ ] The Data Manager opens on this rig's data folder.
- [ ] New → Cell inside a slice creates `.01` with its ID filled in.

## Startup failures

| Symptom | Cause | Fix |
|---|---|---|
| `RuntimeError: No modules loaded during startup` | started with `-n` and no `-m`, or every module failed | add `-m "Data Manager"`, or read the earlier errors |
| `Failed to load device adapter "…" from "…mmgr_dal_….dll"` | pymmcore's device interface doesn't match the Micro-Manager install | see [Micro-Manager cameras](#micro-manager-cameras) |
| `Port COMx is already in use` / `Could not find Scientifica device with description "…"` | another acq4, LinLab, or a crashed acq4 still holds the port | close it; check `Get-Process python`; power-cycle only if needed |
| `Error while initializing Scientifica device at comX … No response received` | logged while acq4 scans all Scientifica ports at startup; that controller is off, busy in another program, or not answering | harmless for controllers this rig doesn't use; for a configured device, close the other program or power-cycle the controller |
| `uses controller version …, but version … expected` (Scientifica) | the device config needs the controller generation | add `version: <n>` to the device config, then re-check speed parameters |
| `ModuleNotFoundError: No module named 'win32api'` | `pywin32` missing (needed by teleprox on Windows) | `pip install pywin32` |
| `No matching distribution found for rtprofile` while installing | environment isn't Python 3.12 | create the env with `python=3.12` |
| `Error importing builtin module … AutomationDebug` (`acq4_automation`) or `Could not import aiccf` | optional upstream features not installed | harmless; ignore |
| `ParseError: Error parsing config file … Missing colon` at line 1 | file saved with a byte-order mark | re-save as UTF-8 without BOM (not PowerShell `Set-Content -Encoding utf8`) |
| `ParseError … \U…` in a path | single backslashes in a Windows path | write paths as `'C:\\Users\\…'` |
| acq4 window closed but `python -m acq4` keeps running | an "ACQ4 Error" dialog is still open | close it (it may be behind other windows); the process then exits |
| Rotary controller has no fast mode | the Scientifica controller's stored top speed was lowered | read it with the driver (`getParam('maxSpeed')`); set it back with approval; see [personalization.md](personalization.md#scientifica-stages) |

## Micro-Manager cameras

pymmcore only loads device adapters built for the same **device interface** version: the 4th number of
`pymmcore.__version__` (e.g. `12.5.1.75.0` → 75). Python 3.12 builds exist only for interface ≥ 71, so older
Micro-Manager installs (e.g. 2021, interface 70) don't work.

- Install a matching Micro-Manager **per user, outside `C:\Program Files\Micro-Manager-2*`** (older acq4
  installs search that pattern automatically). Tested build for interface 75: `MMSetup_64bit_2.0.3_20261014.exe`.
- Point the camera at it with `path: 'C:\\Users\\<you>\\Micro-Manager-…'` in its `devices.cfg` section.
- Check without touching hardware: `lab_check_config.py` loads the adapter without initializing the camera.
