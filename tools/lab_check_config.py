"""Check a machine's acq4 configuration against the installed acq4 before first run.

Verifies that every device driver and module class in the config exists, that the config uses the
shared lab folderTypes.cfg, that the storage directory exists, and that each Micro-Manager camera's
device adapter can be loaded by the installed pymmcore (device interface versions must match).
Nothing is initialized, so no hardware is touched.

usage: python tools/lab_check_config.py [path/to/default.cfg]
"""
import getpass
import os
import socket
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pyqtgraph as pg

app = pg.mkQApp()
from pyqtgraph import configfile
from acq4 import devices, modules

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_FOLDER_TYPES = os.path.join(REPO, "config", "folderTypes.cfg")

failures = 0


def report(status, msg):
    global failures
    if status == "FAIL":
        failures += 1
    print("%-4s  %s" % (status, msg))


def readConfig(path):
    return configfile.readConfigFile(
        os.path.abspath(path),
        hostname=socket.gethostname(),
        username=getpass.getuser(),
        environ=os.environ,
        configpath=os.path.dirname(os.path.abspath(path)),
    )


def checkMicroManager(name, dcfg):
    try:
        import pymmcore
    except ImportError:
        report("FAIL", "%s: pymmcore is not installed (pip install -e .[micromanager])" % name)
        return
    from acq4.util import micromanager

    paths = [dcfg["path"]] if dcfg.get("path") else micromanager.microManagerPaths
    if not paths:
        report("FAIL", "%s: no Micro-Manager folder found; set 'path:' in the device config" % name)
        return
    apiVersion = pymmcore.__version__.split(".")[3]
    os.environ["PATH"] = os.environ["PATH"] + ";" + ";".join(paths)
    mmc = pymmcore.CMMCore()
    mmc.setDeviceAdapterSearchPaths(paths)
    try:
        mmc.loadDevice(name, dcfg["mmAdapterName"], dcfg["mmDeviceName"])
        report("OK", "%s: adapter %s loads from %s (device interface %s)"
               % (name, dcfg["mmAdapterName"], paths, apiVersion))
    except Exception as e:
        report("FAIL", "%s: cannot load adapter %s from %s with pymmcore device interface %s. Install a "
               "Micro-Manager build with that interface and set 'path:' (see LAB_INSTALL.md). Error: %s"
               % (name, dcfg["mmAdapterName"], paths, apiVersion, e))
    finally:
        mmc.unloadAllDevices()


def main():
    cfgFile = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "config", "default.cfg")
    if not os.path.isfile(cfgFile):
        report("FAIL", "config file not found: %s (copy this machine's config into acq4U\\config)" % cfgFile)
        return
    print("Checking", cfgFile, "\n")
    cfg = readConfig(cfgFile)
    modules.importBuiltinClasses()

    for name, dcfg in (cfg.get("devices") or {}).items():
        driver = dcfg.get("driver")
        try:
            devices.getDeviceClass(driver)
            report("OK", "device %s (driver %s)" % (name, driver))
        except Exception as e:
            report("FAIL", "device %s: unknown driver %r (%s)" % (name, driver, e))
            continue
        if driver == "MicroManagerCamera":
            checkMicroManager(name, dcfg)

    for name, mcfg in (cfg.get("modules") or {}).items():
        try:
            modules.getModuleClass(mcfg.get("module"))
            report("OK", "module %s (%s)" % (name, mcfg.get("module")))
        except Exception as e:
            report("FAIL", "module %s: %s" % (name, e))

    misc = cfg.get("misc") or {}
    shared = readConfig(SHARED_FOLDER_TYPES)
    if misc.get("folderTypes") == shared:
        report("OK", "folderTypes matches the shared lab config/folderTypes.cfg")
    else:
        report("FAIL", "folderTypes differs from the shared lab file; default.cfg should contain "
               "folderTypes: readConfigFile('folderTypes.cfg') and config\\folderTypes.cfg should not be edited locally")

    storage = misc.get("storageDir")
    if storage and os.path.isdir(storage):
        report("OK", "storageDir exists: %s" % storage)
    else:
        report("FAIL", "storageDir does not exist: %r" % storage)

    print("\n%s" % ("All checks passed." if failures == 0 else "%d problem(s) found." % failures))


if __name__ == "__main__":
    main()
    sys.exit(1 if failures else 0)
