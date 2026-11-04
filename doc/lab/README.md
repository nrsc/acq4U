# acq4U lab docs (for agents and maintainers)

acq4U is official acq4 plus the lab's features and fixes. It lives at `github.com/nrsc/acq4U` (private).
These docs describe how the lab version differs from upstream, how to run and debug it, and how to change it
safely. Humans setting up a rig should start with [`LAB_INSTALL.md`](../../LAB_INSTALL.md).

| Doc | Read it when you need to |
|---|---|
| [integration.md](integration.md) | change lab code, merge a new upstream acq4 release, or run the lab tests |
| [startup.md](startup.md) | launch acq4U, understand the startup sequence, or fix a startup failure |
| [personalization.md](personalization.md) | change folder types, notebook export columns, required fields, or per-rig settings |
| [error-logging.md](error-logging.md) | find logs, read an error, or match a symptom to a known cause |

Upstream's `AGENTS.md`, `CLAUDE.md` and `CONTRIBUTING.md` still apply. These docs add lab-specific rules.

## Rules for working in this repo

- **Shared vs per-machine config.** Git tracks only `config/folderTypes.cfg` (shared by every rig). Everything
  else in `config/` (`default.cfg`, `devices.cfg`, `devices/`, `modules/`, `protocols/`) belongs to one machine
  and must never be committed. `.gitignore` enforces this (`config/*` ignored, `!config/folderTypes.cfg`).
- **Hardware is not a test fixture.** Don't initialize, move, or reconfigure real devices unless the user asks.
  Use `-d <device>` / `-D` or the mock config for tests. Settings written to Scientifica controllers
  (`setParam`, `setSpeed`, `setUserSpeed`) are stored permanently in the controller and survive power cycles.
- **One acq4 at a time.** Two acq4 instances (or acq4 plus LinLab) cannot share a serial port or camera.
  Check for a running `python -m acq4` process before touching hardware, `.index` files, or the log folder.
- **Data on disk is the lab's record.** Don't edit `.index` files in `acq4_data` while acq4 is running (it
  caches them). Make changes through `acq4.util.DataManager` handles, never by rewriting the files.
- **Tests before push.** After changing lab code or merging upstream, run `tools/lab_featuretest.py` and
  `tools/lab_renametest.py` (see [integration.md](integration.md#tests)). Both use mock devices and scratch data.
- **Commits.** Follow upstream `CLAUDE.md`: `<type>: <description>`, an author that includes "(claude)" for
  agent-written commits, and the "Generated with Claude Code" line. Push to `origin` (nrsc/acq4U) `main`.
- **No upstream CI.** The upstream GitHub workflows (auto version bump, tests) are disabled in nrsc/acq4U on
  purpose. Don't re-enable them without asking; the version number in `acq4/__init__.py` is not meaningful.
