# Installing the lab's acq4 (acq4U) on a rig machine

acq4U is official acq4 (0.10.41) plus the lab's features:

- **Camera module:** Export Mosaic, drag-and-drop pinning from the Data Manager, and a fix for pinned frames
  covering the live image.
- **Data Manager:** Export Metadata for the joint notebook, and `.01`, `.02`… cell naming with automatic IDs.

These steps install it on another Windows rig. That rig keeps its own hardware and camera settings and gets the
shared lab folder types.

| Comes from git (same on every machine) | Stays on each machine (never touched by git) |
|---|---|
| acq4 code with the lab features | `config\default.cfg` (storage folder, modules) |
| `config\folderTypes.cfg` (folder types and dropdowns) | `config\devices.cfg` and `config\devices\` (hardware, camera, calibrations) |
| `tools\lab_check_config.py`, `tools\lab_featuretest.py` | `config\modules\` (window layouts), `config\protocols\` |

The machine's existing acq4 install is not modified. Keep it as a fallback until acq4U is working.

Commands below are for **PowerShell**. Replace `<you>` with the Windows user name.

## Before you start

- **Anaconda or Miniconda** and **Git for Windows** are installed.
- **GitHub access:** your GitHub account can read the private repo `nrsc/acq4U`. Ask Scott Sawchuk for access,
  then set up an SSH key or run `gh auth login`.
- **Hardware drivers:** vendor drivers for the rig's hardware are already installed, as they were for the old
  acq4. For example, Thorlabs ThorCam/uc480 for a Thorlabs camera.
- **Close acq4:** two copies of acq4 cannot control the same hardware at once.

## 1. Get the code

```powershell
git clone git@github.com:nrsc/acq4U.git C:\Users\<you>\acq4U
cd C:\Users\<you>\acq4U
```

## 2. Create the Python environment

acq4U needs Python 3.12. It uses its own environment, `acq4U`, so the old acq4 environment keeps working.

```powershell
conda create -n acq4U python=3.12 -y
conda activate acq4U
pip install -e ".[micromanager,scientifica]" pywin32
```

Choose the extras in `[...]` from the active (uncommented) `driver:` lines in the rig's `devices.cfg`:

| `driver:` in devices.cfg | extra |
|---|---|
| `MicroManagerCamera`, `MicroManagerStage` | `micromanager` |
| `Scientifica` | `scientifica` |
| `Sensapex` | `sensapex` |
| `MultiClamp` | `multiclamp` |
| `NiDAQ` (also used by `DAQGeneric` channels) | `nidaq` |
| `ThorlabsMFC1` and other Thorlabs serial devices | `thorlabs` |

Separate several extras with commas, e.g. `".[micromanager,scientifica,multiclamp]"`. Always include `pywin32`,
because acq4 needs it on Windows.

> If `conda activate` does nothing in PowerShell, run `conda init powershell` once and open a new window.
> On conda 22.x, creating or renaming environments may need the base environment active first (`conda activate base`).

## 3. Bring over this machine's configuration

Copy the machine's existing acq4 config into acq4U, **except `folderTypes.cfg`**, which comes from git:

```powershell
robocopy C:\path\to\old\acq4\config C:\Users\<you>\acq4U\config /E /XF folderTypes.cfg /XD example
```

Then open `config\default.cfg` and check that:

- the `misc:` section contains `folderTypes: readConfigFile('folderTypes.cfg')` (it loads the shared file);
- `storageDir:` points at this machine's data folder.

**No previous acq4 on this machine?** Start from `config\example\` (simulated devices): copy everything except
`folderTypes.cfg` into `config\`, then edit `devices.cfg` for this rig's hardware.

Edit config files in Notepad or VS Code. Don't edit them with PowerShell's `Set-Content -Encoding utf8`: it adds
a byte-order mark that acq4 cannot read.

Don't edit `config\folderTypes.cfg` on just one machine. Change it for everyone instead (see
[Changing the shared folder types](#changing-the-shared-folder-types)).

## 4. Micro-Manager cameras only

Skip this step unless `devices.cfg` has `driver: 'MicroManagerCamera'`.

acq4U's Micro-Manager link (pymmcore) only works with a Micro-Manager build whose **device interface version**
matches it. Older Micro-Manager installs (e.g. the 2021 `C:\Program Files\Micro-Manager-2.0`) are too old.

1. **Check the version pymmcore needs.** It's the 4th number of the pymmcore version, e.g. `12.5.1.75.0` → `75`:

   ```powershell
   python -c "import pymmcore; print(pymmcore.__version__)"
   ```

2. **Install a matching Micro-Manager next to the old one.** For interface 75, use the tested build
   `MMSetup_64bit_2.0.3_20261014.exe` from https://download.micro-manager.org/nightly/2.0/Windows/. Download it,
   then install it silently, per user, into its own folder:

   ```powershell
   Start-Process -Wait -FilePath "$env:USERPROFILE\Downloads\MMSetup_64bit_2.0.3_20261014.exe" -ArgumentList `
     '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS', `
     '/DIR="C:\Users\<you>\Micro-Manager-2.0.3-20261014"'
   ```

   **Do not install it under `C:\Program Files\Micro-Manager-2...`.** The old acq4 automatically searches every
   folder matching that name and could load the wrong adapters.

3. **Point the camera at it.** In `config\devices.cfg`, add a `path:` line to the camera's section:

   ```
   Camera:
       driver: 'MicroManagerCamera'
       path: 'C:\\Users\\<you>\\Micro-Manager-2.0.3-20261014'
       mmAdapterName: ...        # unchanged
   ```

The camera's vendor driver must still be installed system-wide, as it was for the old acq4.

## 5. Check the setup

```powershell
python tools\lab_check_config.py
```

This checks every device driver and module, the shared folder types, the storage folder, and whether each
Micro-Manager camera adapter loads. It doesn't initialize any hardware. Fix any `FAIL` lines before running acq4.

Optionally, run the feature test. It uses simulated devices and copies of real data in a scratch folder:

```powershell
python -u tools\lab_featuretest.py $env:TEMP\acq4U_test C:\Users\<you>\acq4U C:\path\to\acq4_data
```

It needs the data folder to contain `Human\H26.03.302` and `Macaque\Nemestrina\QN26.26.038` (or edit those names
in the script). It should end with `21/21 checks passed`.

## 6. Run acq4U

Close any other acq4 first, then:

```powershell
conda activate acq4U
cd C:\Users\<you>\acq4U
python -m acq4
```

On the first run, check:

- [ ] the camera shows live video;
- [ ] the stage and focus respond;
- [ ] the Data Manager opens on the right data folder;
- [ ] New → Cell inside a slice creates `.01` with its ID filled in;
- [ ] Export Metadata copies a row that pastes correctly into the notebook.

## Updating

```powershell
conda activate acq4U
cd C:\Users\<you>\acq4U
git pull
pip install -e ".[micromanager,scientifica]" pywin32   # only needed if dependencies changed
python tools\lab_check_config.py
```

`git pull` brings new lab features and the current shared folder types. This machine's own config files are
never changed by it.

## Changing the shared folder types

1. Edit `config\folderTypes.cfg`.
2. Commit and push the change:

   ```powershell
   git add config\folderTypes.cfg
   git commit -m "chore: <what changed in folder types>"
   git push
   ```

3. On every other machine, run `git pull` and restart acq4.

`git status` lists `config\folderTypes.cfg` as modified if someone edited it locally without sharing the change.

## Differences from the old acq4 to expect

- **Folders created lowercase by earlier acq4U builds.** Before 2026-11-04, acq4U showed every folder name in
  lowercase and created new folders in lowercase (a new Donor was `donor_000`). That is fixed: names now show
  and are created with their real capitalization. Folders already created lowercase stay that way until renamed.
- **`Patch` is deprecated.** The `Patch` module still loads but is replaced by MultiPatch.
- **Atlas warning is harmless.** An `aiccf` import error at startup only means the optional brain-atlas overlay
  isn't installed.

## Merging a new official acq4 release (maintainers)

This repo is official acq4 with the lab's commits on top. To bring in a newer acq4 release:

```powershell
git remote add upstream https://github.com/acq4/acq4.git   # once per checkout
git fetch upstream
git merge upstream/main
pip install -e ".[micromanager,scientifica]" pywin32
python -u tools\lab_featuretest.py $env:TEMP\acq4U_test C:\Users\<you>\acq4U C:\path\to\acq4_data
python -u tools\lab_renametest.py $env:TEMP\acq4U_test C:\Users\<you>\acq4U
python tools\lab_check_config.py
```

Conflicts are most likely in the files carrying lab features or fixes:

- `acq4\util\imaging\imaging_ctrl.py` and `imaging_template.ui`;
- `acq4\modules\Camera\CameraWindow.py`;
- `acq4\modules\DataManager\DataManagerModule.py` and `DataManagerTemplate.ui`;
- `acq4\util\DirTreeWidget\DirTreeWidget.py`;
- `acq4\logging_config.py`, `acq4\Manager.py` (`logFileReleased`) and `acq4\util\DataManager\dot_index.py`
  (renaming folders that hold the log file on Windows);
- `acq4\util\DataManager\common.py` and `__init__.py` (handles keep on-disk capitalization on Windows);
- `acq4\modules\MosaicEditor\MosaicEditor.py` and `acq4\util\Canvas\items\CellCanvasItem.py` (Mosaic Editor Save and
  folder loading);
- `acq4\devices\Scientifica\scientifica.py` (manual-control speed defaults to the controller's own top speed).

Push only after both tests pass. If the new acq4 needs a newer pymmcore, also install a Micro-Manager
build with the matching device interface (step 4).

## Going back to the old acq4

Nothing in the old install was changed. Close acq4U, then start the old acq4 from its own environment as before.
