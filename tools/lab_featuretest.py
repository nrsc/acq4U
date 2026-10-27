"""Integration test of the lab features: real acq4 Manager + modules on mock devices and scratch data.

Copies the example (mock) config with the lab folderTypes.cfg, copies .index files and 5 mosaic
images from a real data folder into <scratch dir>, then exercises cell naming, metadata export,
pin z-order, drag-and-drop pinning, Load pinned images and mosaic export. Run after upgrading acq4.

usage: python tools/lab_featuretest.py <scratch dir> <acq4U repo> <real acq4_data dir>
"""
import glob
import json
import os
import re
import shutil
import sys
import time
import types
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
SCR, REPO, REAL = sys.argv[1:4]
ROOT = os.path.join(SCR, "acq4U_test")
shutil.rmtree(ROOT, ignore_errors=True)
DATA = os.path.join(ROOT, "data")
CFG = os.path.join(ROOT, "config")

# ---- scratch config: example (mock) devices + our folderTypes, storage in scratch data
shutil.copytree(os.path.join(REPO, "config", "example"), CFG)
shutil.copy(os.path.join(REPO, "config", "folderTypes.cfg"), os.path.join(CFG, "folderTypes.cfg"))
cfgText = open(os.path.join(CFG, "default.cfg"), encoding="utf-8").read()
cfgText = re.sub(r"(?m)^(\s*)storageDir:.*$", lambda m: m.group(1) + "storageDir: %r" % DATA, cfgText, count=1)
open(os.path.join(CFG, "default.cfg"), "w", encoding="utf-8").write(cfgText)

# ---- scratch data: real .index files for two slices, plus 5 real mosaic images
for rel in ["Human/H26.03.302", "Macaque/Nemestrina/QN26.26.038"]:
    for f in glob.glob(os.path.join(REAL, rel, "**", ".index"), recursive=True, include_hidden=True):
        if "mosaic_" in f:
            continue
        dst = os.path.join(DATA, os.path.relpath(f, REAL))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(f, dst)
for sub in ["", "Human", "Macaque", "Macaque/Nemestrina"]:
    open(os.path.join(DATA, sub, ".index"), "a").close() if not os.path.exists(os.path.join(DATA, sub, ".index")) else None
srcMosaic = os.path.join(REAL, "Human/H26.03.302/.11.21/mosaic_000")
dstMosaic = os.path.join(DATA, "Human/H26.03.302/.11.21/mosaic_000")
os.makedirs(dstMosaic, exist_ok=True)
shutil.copy(os.path.join(srcMosaic, ".index"), dstMosaic)
for n in range(5):
    shutil.copy(os.path.join(srcMosaic, "image_%03d.tif" % n), dstMosaic)

import pyqtgraph as pg

app = pg.mkQApp()
from acq4.Manager import Manager
from acq4.util import Qt
from acq4.util.DataManager import getHandle

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print("%s  %s  %s" % ("PASS" if ok else "FAIL", name, detail))


def pump(seconds=0.2):
    t = time.time()
    while time.time() - t < seconds:
        app.processEvents()
        time.sleep(0.01)


args = Manager.makeArgParser().parse_args(["-c", os.path.join(CFG, "default.cfg"), "-n", "-b", DATA, "-m", "Data Manager", "-m", "Camera"])
man = Manager.runFromCommandLine(args)
pump(1)
print("Manager up; devices:", list(man.devices.keys())[:8], "...")

dm = man.getModule("Data Manager")
cam = man.getModule("Camera")
pump(1)
base = man.getBaseDir()
slc = getHandle(os.path.join(DATA, "Human/H26.03.302/.11.21"))

# ---- A. tree drag exports file URLs
tree = dm.ui.fileTreeWidget
tree.select(slc)
pump()
md = tree.mimeData(tree.selectedItems())
check("tree drag carries file URLs", md.hasUrls() and md.urls()[0].toLocalFile().endswith(".11.21"),
      md.urls()[0].toLocalFile() if md.hasUrls() else "")

# ---- B. new cell naming + ID autofill + rename sync
man.setCurrentDir(slc)
pump()
cellIdx = dm.ui.newFolderList.findText("Cell")
dm.ui.newFolderList.setCurrentIndex(cellIdx)  # triggers newFolder
pump()
newCell = man.getCurrentDir()
check("new cell named .05 in slice", newCell.shortName() == ".05" and newCell.parent() is slc, newCell.name(relativeTo=base))
check("new cell ID autofilled", newCell.info().get("ID") == "H26.03.302.11.21.05", newCell.info().get("ID"))
man.setCurrentDir(getHandle(dstMosaic))
dm.ui.newFolderList.setCurrentIndex(cellIdx)
pump()
c6 = man.getCurrentDir()
check("cell created from mosaic folder lands in slice", c6.shortName() == ".06" and c6.parent() is slc, c6.name(relativeTo=base))
# rename the way a user does: edit the item in the Data Manager tree (fires the real rename signals)
tree.select(c6)
pump()
tree.item(c6).setText(0, ".09")
pump()
renamed = getHandle(os.path.join(slc.name(), ".09"))
diskID = re.search(r"ID: '([^']*)'", open(os.path.join(renamed.name(), ".index")).read()).group(1)
check("rename in tree updates autofilled ID", os.path.isdir(renamed.name()) and diskID == "H26.03.302.11.21.09", diskID)

# ---- C. metadata export (dialog choice mocked)
tree.select(slc)
pump()
dm.fileSelectionChanged()
shown = []
with mock.patch.object(type(dm).__mro__[0].__module__ and __import__("acq4.modules.DataManager.metadata_dialog", fromlist=["x"]).MissingMetadataDialog,
                       "exec_", lambda self: (shown.append([(h.shortName(), f.name) for h, f in self.fields]), setattr(self, "choice", "export"))):
    dm.exportMetadataClicked()
clip = Qt.QApplication.clipboard().text().splitlines()
check("metadata dialog listed missing fields", len(shown) == 1 and len(shown[0]) > 0, str(shown[0][:4]) if shown else "")
check("metadata rows copied (6 cells, culture layout 32 cols)", len(clip) == 6 and {len(l.split("\t")) for l in clip} == {32},
      "%d rows x %s" % (len(clip), {len(l.split("\t")) for l in clip}))
csvs = glob.glob(os.path.join(DATA, ".metadata", "*.csv"))
check("metadata CSV written to .metadata", len(csvs) == 1, os.path.basename(csvs[0]) if csvs else "")
nhp = getHandle(os.path.join(DATA, "Macaque/Nemestrina/QN26.26.038/.19.07"))
tree.select(nhp)
pump()
with mock.patch("acq4.modules.DataManager.metadata_dialog.MissingMetadataDialog.exec_", lambda self: setattr(self, "choice", "export")):
    dm.exportMetadataClicked()
clip = Qt.QApplication.clipboard().text().splitlines()
check("NHP rows use NHP layout (28 cols)", {len(l.split("\t")) for l in clip} == {28} and clip[0].split("\t")[1] == "M.nemestrina",
      "%s | species=%s" % ({len(l.split("\t")) for l in clip}, clip[0].split("\t")[1]))

# ---- D. camera: live pins stay under live image
iface = cam.ui.interfaces["Camera"]
ictrl = iface.imagingCtrl
iface.getDevice().start()
for _ in range(100):
    pump(0.05)
    if ictrl.frameDisplay.currentFrame is not None:
        break
check("mock camera produces frames", ictrl.frameDisplay.currentFrame is not None)
for _ in range(120):
    ictrl.pinCurrentFrame()
live = ictrl.frameDisplay.imageItem()
liveTop = live
while liveTop.parentItem() is not None and liveTop.parentItem() is not live.getViewBox().childGroup:
    liveTop = liveTop.parentItem()
maxPinZ = max(p.zValue() for p in ictrl.pinnedFrames)
check("120 live pins all below live image", maxPinZ < liveTop.zValue(), "max pin z=%s, live z=%s" % (maxPinZ, liveTop.zValue()))
iface.getDevice().stop()
pump(0.5)
ictrl.clearPinnedFrames()

# ---- E. drag-and-drop pinning (real drop event through the event filter)
mdDrop = Qt.QMimeData()
mdDrop.setUrls([Qt.QUrl.fromLocalFile(dstMosaic)])
ev = Qt.QDropEvent(pg.QtCore.QPointF(5, 5), Qt.Qt.CopyAction | Qt.Qt.MoveAction, mdDrop, Qt.Qt.LeftButton, Qt.Qt.NoModifier)
handled = cam.ui.eventFilter(cam.ui._dropTarget, ev)
pump(1)
check("drop accepted as copy", handled and ev.dropAction() == Qt.Qt.CopyAction)
check("dropped mosaic folder pinned 5 images with source files", len(ictrl.pinnedFrames) == 5 and all(p.pinnedFile is not None for p in ictrl.pinnedFrames),
      "%d pins" % len(ictrl.pinnedFrames))
p0 = ictrl.pinnedFrames[0]
expected = p0.pinnedFrame.globalTransform().map(pg.Vector(0, 0, 0))
got = p0.mapToView(pg.Point(0, 0))
check("pinned image placed at saved stage position", abs(got.x() - expected.x()) < 1e-9 and abs(got.y() - expected.y()) < 1e-9,
      "(%.6f, %.6f)" % (got.x(), got.y()))

# ---- F. upstream "Load pinned images" keeps sources too
ictrl.clearPinnedFrames()
man.setCurrentDir(getHandle(dstMosaic))
dm.loadPinnedImages()
pump(0.5)
check("Load pinned images button pins with sources", len(ictrl.pinnedFrames) == 5 and all(p.pinnedFile is not None for p in ictrl.pinnedFrames))

# ---- G. mosaic export: 5 file-backed pins + 2 live pins
iface.getDevice().start()
pump(1.5)
ictrl.pinCurrentFrame()
pump(0.3)
ictrl.pinCurrentFrame()
iface.getDevice().stop()
pump(0.5)
man.setCurrentDir(slc)
mosaicFile = os.path.join(DATA, ".mosaics", "test.mosaic")
os.makedirs(os.path.dirname(mosaicFile), exist_ok=True)
check("default mosaic name follows folder", ictrl.defaultMosaicFileName().endswith(os.path.join(".mosaics", "H26.03.302.11.21.mosaic")),
      ictrl.defaultMosaicFileName())
n = ictrl.exportMosaic(mosaicFile)
state = json.load(open(mosaicFile))
newMosaicDirs = sorted(d for d in os.listdir(slc.name()) if d.startswith("mosaic_") and d != "mosaic_000")
check("mosaic export wrote 7 items", n == 7 and len(state["items"]) == 7, "%d items" % len(state["items"]))
check("live pins saved into new mosaic folder", newMosaicDirs == ["mosaic_001"] and len(glob.glob(os.path.join(slc.name(), "mosaic_001", "*.tif"))) == 2,
      str(newMosaicDirs))

me = man.loadModule("MosaicEditorModule", "Mosaic Editor")
pump(0.5)
me.editor.loadStateFile(mosaicFile)
pump(0.5)
items = sorted(me.editor.canvas.items, key=lambda i: i.zValue())
check("Mosaic Editor reloads all 7 images", len(items) == 7, "%d items" % len(items))

print("\n%d/%d checks passed" % (sum(ok for _, ok in results), len(results)))
man.quit()
pump(0.5)
os._exit(0 if all(ok for _, ok in results) else 1)
