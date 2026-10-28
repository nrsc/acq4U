"""Regression test: folders holding the acq4 log can be renamed on Windows.

acq4 keeps log.json open in the current experiment folder (Day, Donor, Slice); Windows refuses to rename a
folder holding an open file. Runs the real Manager on mock devices in a scratch folder: creates Day/Donor/Slice
folders, renames them through the Data Manager tree, and checks the log follows and no index entry is lost.

usage: python tools/lab_renametest.py <scratch dir> <acq4U repo>
"""
import logging
import os
import re
import shutil
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
SCR, REPO = sys.argv[1:3]
ROOT = os.path.join(SCR, "rename_test")
shutil.rmtree(ROOT, ignore_errors=True)
DATA = os.path.join(ROOT, "data")
CFG = os.path.join(ROOT, "config")
os.makedirs(DATA)
shutil.copytree(os.path.join(REPO, "config", "example"), CFG)
shutil.copy(os.path.join(REPO, "config", "folderTypes.cfg"), os.path.join(CFG, "folderTypes.cfg"))
t = open(os.path.join(CFG, "default.cfg"), encoding="utf-8").read()
t = re.sub(r"(?m)^(\s*)storageDir:.*$", lambda m: m.group(1) + "storageDir: %r" % DATA, t, count=1)
open(os.path.join(CFG, "default.cfg"), "w", encoding="utf-8").write(t)
open(os.path.join(DATA, ".index"), "w").write(".:\n    __timestamp__: %r\n" % time.time())

import pyqtgraph as pg

app = pg.mkQApp()
from acq4.Manager import Manager
from acq4.util.DataManager import getHandle

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print("%s  %s  %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)


def pump(s=0.3):
    t0 = time.time()
    while time.time() - t0 < s:
        app.processEvents()
        time.sleep(0.01)


man = Manager.runFromCommandLine(Manager.makeArgParser().parse_args(
    ["-c", os.path.join(CFG, "default.cfg"), "-n", "-b", DATA, "-m", "Data Manager"]))
dm = man.getModule("Data Manager")
tree = dm.ui.fileTreeWidget
pump(1)


def newFolder(ftype, where):
    man.setCurrentDir(where)
    pump()
    dm.ui.newFolderList.setCurrentIndex(dm.ui.newFolderList.findText(ftype))
    pump()
    return man.getCurrentDir()


def renameInTree(handle, newName):
    tree.select(handle)
    pump()
    tree.item(handle).setText(0, newName)  # same path as a user editing the name
    pump()


def indexKeys(d):
    return re.findall(r"(?m)^(\S[^:\n]*):", open(os.path.join(d, ".index")).read())


day = newFolder("Day", getHandle(DATA))
donorA = newFolder("Donor", day)
logPath = man._logFile.name()
check("log moved into new donor", os.path.dirname(logPath) == donorA.name(), os.path.relpath(logPath, DATA))

renameInTree(donorA, "B767b")
newDonor = os.path.join(day.name(), "B767b")
check("rename donor holding the log succeeds", os.path.isdir(newDonor) and not os.path.exists(os.path.join(day.name(), "donor_000")),
      str(sorted(os.listdir(day.name()))))
check("parent .index keeps the donor entry", "B767b" in indexKeys(day.name()) and "donor_000" not in indexKeys(day.name()),
      str(indexKeys(day.name())))
logging.getLogger("acq4").warning("message after rename")
pump()
check("log keeps writing at the new path", os.path.dirname(man._logFile.name()).lower().endswith("b767b")
      and "message after rename" in open(os.path.join(newDonor, "log.json"), encoding="utf-8").read(),
      os.path.relpath(man._logFile.name(), DATA))

# a donor that held the log earlier (log has moved on) must also be renamable: old file handles closed
donorB = newFolder("Donor", day)
sliceB = newFolder("Slice", donorB)
check("log moved on to the slice", os.path.dirname(man._logFile.name()) == sliceB.name())
renameInTree(getHandle(newDonor), "B767b_renamed")
check("rename a donor that previously held the log", os.path.isdir(os.path.join(day.name(), "B767b_renamed")),
      str(sorted(os.listdir(day.name()))))
renameInTree(donorB, "C111")
check("rename donor whose child slice holds the log", os.path.isdir(os.path.join(day.name(), "C111")),
      str(sorted(os.listdir(day.name()))))

# a rename Windows refuses must not drop the folder's entry from the parent index
donorC = newFolder("Donor", day)
man.setCurrentDir(getHandle(os.path.join(day.name(), "C111")))
pump()
blocker = open(os.path.join(donorC.name(), "held_open.txt"), "w")
renameInTree(donorC, "D222")
blocker.close()
check("refused rename leaves folder and index entry intact",
      os.path.isdir(donorC.name()) and donorC.shortName() in indexKeys(day.name()),
      "%s | %s" % (sorted(os.listdir(day.name())), indexKeys(day.name())))

print("\n%d/%d checks passed" % (sum(results), len(results)), flush=True)
man.quit()
pump(0.5)
os._exit(0 if all(results) else 1)
