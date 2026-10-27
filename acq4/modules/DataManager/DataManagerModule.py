import contextlib
import json
import os
import re
import time
from datetime import datetime
from logging import LogRecord

from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.DataManager import getDataManager, getHandle, DirHandle, FileHandle
from acq4.util.StatusBar import StatusBar
from pyqtgraph import FileDialog
from teleprox.log.logviewer import LogViewer
from . import FileAnalysisView
from . import metadata_export
from .metadata_dialog import MissingMetadataDialog
from ...logging_config import get_logger, HistoricLogRecord
from ...util.HelpfulException import HelpfulException

logger = get_logger(__name__)
Ui_MainWindow = Qt.importTemplate('.DataManagerTemplate')


class Window(Qt.QMainWindow):
    sigClosed = Qt.Signal()

    def closeEvent(self, ev, **kwargs):
        ev.accept()
        self.sigClosed.emit()


def load_log_records_legacy(log_file):
    records = []
    msgType_to_level = {
        'status': 20,
        'error': 40,
        'warning': 30,
    }
    try:
        entries = log_file.read()
    except Exception:
        logger.exception(f"Error reading log from {log_file.name()}")
        return records
    for name, entry in entries.items():
        try:
            exc_info = (
                entry['exception']['message'] + ''.join(entry['exception']['traceback'])
                if entry.get('exception', None) is not None
                else None
            )
            r = LogRecord(
                name="acq4",
                msg=entry['message'],
                level=msgType_to_level.get(entry['msgType'], 20),
                pathname='',
                lineno=0,
                args=None,
                exc_info=exc_info,
            )
            r.created = datetime.fromisoformat(entry['timestamp']).timestamp()
            records.append(r)
        except Exception:
            logger.exception(f"Error making log record from {log_file.name()}:{name}")
    return records


def load_log_records(log_file):
    records = []
    for line in log_file.readlines():
        records.append(HistoricLogRecord(**(json.loads(line))))
    return records


class DataManager(Module):
    moduleDisplayName = "Data Manager"
    moduleCategory = "Acquisition"

    sigAnalysisDbChanged = Qt.Signal()

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.dm = getDataManager()
        self.win = Window()
        mp = os.path.dirname(__file__)
        self.win.setWindowIcon(Qt.QIcon(os.path.join(mp, 'icon.png')))
        self.win.dm = self  ## so embedded widgets can find the module easily
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self.win)
        self.ui.analysisWidget = FileAnalysisView.FileAnalysisView(self.ui.analysisTab, self)
        self.ui.analysisTab.layout().addWidget(self.ui.analysisWidget)
        self.ui.logWidget = LogViewer(logger=None)
        self._logFile = None
        self.ui.logTab.layout().addWidget(self.ui.logWidget)

        self.win.show()
        w = self.ui.splitter.width()
        self.ui.splitter.setSizes([int(w * 0.4), int(w * 0.6)])
        self.ui.logDock.hide()
        self.dialog = None
        self.ui.fileTreeWidget.setSelectionMode(Qt.QAbstractItemView.ExtendedSelection)
        try:
            self.baseDirChanged()
        except Exception:
            logger.exception("Could not set base directory:")
        try:
            self.currentDirChanged()
        except Exception:
            logger.exception("Could not set current directory:")

        self.selFile = None
        self.updateNewFolderList()

        self.manager.sigBaseDirChanged.connect(self.baseDirChanged)
        self.manager.sigConfigChanged.connect(self.updateNewFolderList)
        self.manager.sigCurrentDirChanged.connect(self.currentDirChanged)
        self.manager.sigLogDirChanged.connect(self.updateLogDir)
        self.ui.analysisWidget.sigDbChanged.connect(self.analysisDbChanged)
        self.ui.baseDirText.editingFinished.connect(self.baseDirTextChanged)
        self.ui.fileDisplayTabs.currentChanged.connect(self.tabChanged)
        self.ui.fileTreeWidget.itemSelectionChanged.connect(self.fileSelectionChanged)
        self.ui.newFolderList.currentIndexChanged.connect(self.newFolder)
        self.ui.selectDirBtn.clicked.connect(self.showFileDialog)
        self.ui.setCurrentDirBtn.clicked.connect(self.setCurrentClicked)
        self.ui.setLogDirBtn.clicked.connect(self.setLogDir)
        self.ui.loadPinnedImagesBtn.clicked.connect(self.loadPinnedImages)
        self.ui.exportMetadataBtn.clicked.connect(self.exportMetadataClicked)
        self.win.sigClosed.connect(self.quit)

        self.win.setStatusBar(StatusBar())

    def updateNewFolderList(self):
        self.ui.newFolderList.clear()
        conf = self.manager._folderTypesConfig()
        self.ui.newFolderList.clear()
        self.ui.newFolderList.addItems(['New...', 'Folder'] + list(conf.keys()))

    def baseDirChanged(self):
        dh = self.manager.getBaseDir()
        self.baseDir = dh
        if dh is None:
            self.ui.baseDirText.setText('')
        else:
            self.ui.baseDirText.setText(dh.name())
        self.ui.fileTreeWidget.setBaseDirHandle(dh)

    def selectFile(self, path):
        if isinstance(path, str):
            path = getHandle(path)
        self.ui.fileTreeWidget.select(path)

    def setLogDir(self):
        d = self.selectedFile()
        if d is None:
            raise ValueError("Select a directory first to set as log directory")
        if not isinstance(d, DirHandle):
            d = d.parent()
        self.manager.setLogDir(d)

    def loadPinnedImages(self):
        from acq4.modules.Camera.CameraWindow import framesWithSources

        cam_mod = self.manager.getModule("Camera")
        current_dir = self.manager.getCurrentDir()
        # keep each image's source file so a mosaic export can reference it
        for frame, fh in framesWithSources(current_dir):
            cam_mod.ui.displayPinnedFrame(frame, fileHandle=fh)

    def exportMetadataClicked(self):
        try:
            cells = metadata_export.findCellDirs(self.selectedFile())
            if len(cells) == 0:
                self.ui.exportMetadataBtn.failure("Select a cell or slice")
                return
            if not self.completeMetadata(cells):
                return

            tab = metadata_export.notebookTab(cells[0])
            note = ""
            if tab is None:
                tab = "Human_acute"
                note = " (slice_type not set; formatted for Human_acute)"
            rows = [metadata_export.cellRow(c) for c in cells]

            # save next to the other exports in <baseDir>/.metadata, named after the cell (or slice)
            name = rows[0]["cell_name"] if len(rows) == 1 else (rows[0]["Slice_ID"] or metadata_export.realName(cells[0].parent()))
            outDir = os.path.join(self.manager.getBaseDir().name(), ".metadata")
            os.makedirs(outDir, exist_ok=True)
            fileName = os.path.join(outDir, name + ".csv")
            with open(fileName, "w", newline="", encoding="utf-8") as fh:
                fh.write(metadata_export.rowsToCsv(rows, tab))

            # tab-separated text pastes into separate cells in Google Sheets
            Qt.QApplication.clipboard().setText(metadata_export.rowsToTsv(rows, tab))
            self.ui.exportMetadataBtn.success("Copied %d row(s)" % len(rows))
            self.win.statusBar().showMessage(
                "%s rows copied to clipboard and saved to %s%s" % (tab, fileName, note), 10000)
        except Exception:
            self.ui.exportMetadataBtn.failure("Error.")
            logger.exception("Error exporting metadata:")

    def completeMetadata(self, cells):
        """Prompt for required fields that are empty. Returns False if the user cancelled."""
        while True:
            missing = metadata_export.missingFields(cells)
            if not missing:
                return True
            dlg = MissingMetadataDialog(missing, self.manager, self.baseDir, self.win)
            dlg.exec_()
            if dlg.choice is None:
                return False
            if dlg.choice == "export" or dlg.save() == 0:
                return True
            # saved something: check again, since e.g. slice_type "culture" makes DIV required

    def updateLogDir(self, d):
        self.ui.logDirText.setText(d.name(relativeTo=self.baseDir))

    def setCurrentClicked(self):
        handle = self.selectedFile()
        if handle is None:
            return
        if not handle.isDir():
            handle = handle.parent()
        self.manager.setCurrentDir(handle)

    def currentDirChanged(self, name=None, change=None, args=()):
        newDir = None
        if change in [None, 'moved', 'renamed', 'parent']:
            try:
                newDir = self.manager.getCurrentDir()
                dirName = newDir.name(relativeTo=self.baseDir)
            except Exception:
                dirName = ""
            self.ui.currentDirText.setText(dirName)
            self.ui.fileTreeWidget.setCurrentDir(newDir)
        elif change == 'children':
            with contextlib.suppress(HelpfulException):
                newDir = self.manager.getCurrentDir()

        has_images = newDir is not None and newDir.hasMatchingChildren(
            lambda f: f.fileType() == "ImageFile" or f.shortName().startswith("ImageSequence_") or (
                f.fileType() == "MetaArray" and 'pixelSize' in f.info()
            )
        )
        self.ui.loadPinnedImagesBtn.setEnabled(has_images)

    def showFileDialog(self):
        bd = self.manager.getBaseDir()
        if self.dialog is None:
            self.dialog = FileDialog()
            self.dialog.setFileMode(Qt.QFileDialog.DirectoryOnly)
            self.dialog.filesSelected.connect(self.setBaseDir)
        if bd is not None:
            self.dialog.setDirectory(bd.name())
        self.dialog.show()

    def baseDirTextChanged(self):
        path = str(self.ui.baseDirText.text())
        if not path.strip():
            self.baseDirChanged()
            return
        if not os.path.isdir(path):
            raise ValueError(f"Path {path} does not exist")
        self.setBaseDir(path)

    def setBaseDir(self, dirName):
        if isinstance(dirName, list):
            if len(dirName) == 1:
                dirName = dirName[0]
            else:
                raise ValueError(f"Invalid dirName: {dirName}")
        if dirName is None:
            return
        if os.path.isdir(dirName):
            self.manager.setBaseDir(dirName)
        else:
            raise ValueError("Storage directory is invalid")

    def selectedFile(self) -> FileHandle | None:
        """Return the currently selected file"""
        items = self.ui.fileTreeWidget.selectedItems()
        if len(items) > 0:
            return items[0].handle
        else:
            return None

    def newFolder(self):
        if self.ui.newFolderList.currentIndex() < 1:
            return

        ftype = str(self.ui.newFolderList.currentText())
        self.ui.newFolderList.setCurrentIndex(0)

        cdir = self.manager.getCurrentDir()
        if not cdir.isManaged():
            cdir.createIndex()

        if ftype == 'Folder':
            nd = cdir.mkdir('NewFolder', autoIncrement=True)
            nd.setInfo({})
            # item = self.model.handleIndex(nd)
            self.ui.fileTreeWidget.editItem(nd)
        else:
            spec = self.manager._folderTypesConfig()[ftype]
            name = time.strftime(spec['name'])

            ## Determine where to put the new directory
            parent = cdir
            try:
                checkDir = cdir
                for i in range(5):
                    if not checkDir.isManaged():
                        break
                    inf = checkDir.info()
                    if 'dirType' in inf and inf['dirType'] == ftype:
                        parent = checkDir.parent()
                        break
                    # else:
                    # print "dir no match:", spec, inf
                    checkDir = checkDir.parent()
            except:
                logger.exception("Error while deciding where to put new folder (using currentDir by default)")

            if ftype == 'Cell' and not (parent.isManaged() and parent.info().get('dirType') == 'Slice'):
                # put the cell in the nearest enclosing Slice (e.g. when the current dir is a mosaic folder)
                checkDir = cdir
                while checkDir is not None and checkDir.isManaged():
                    if checkDir.info().get('dirType') == 'Slice':
                        parent = checkDir
                        break
                    checkDir = checkDir.parent()

            ## make
            if ftype == 'Cell' and parent.isManaged() and parent.info().get('dirType') == 'Slice':
                # cells in a slice are numbered .01, .02, ... (lab naming convention)
                nd = parent.mkdir(self._nextCellName(parent))
            else:
                nd = parent.mkdir(name, autoIncrement=True)

            ## Add meta-info
            info = {'dirType': ftype}
            if spec.get('experimentalUnit', False):
                info['expUnit'] = True
            if ftype == 'Cell':
                # autofill; kept in sync with the folder name when it is renamed (see selectedFileAltered)
                info['ID'] = metadata_export.autoCellID(nd)
            nd.setInfo(info)

            self.ui.fileTreeWidget.refresh(
                parent)  ## fileTreeWidget waits a while before updating; force it to refresh immediately.
            self.ui.fileTreeWidget.select(nd)

        logger.info(f"Created new folder: {nd.name(relativeTo=self.baseDir)}")
        self.manager.setCurrentDir(nd)

    def fileSelectionChanged(self):
        # print "file selection changed"
        if self.selFile is not None:
            with contextlib.suppress(TypeError):
                self.selFile.sigChanged.disconnect(self.selectedFileAltered)
        fh = self.selectedFile()
        self.manager.currentFile = fh  ## Make this really easy to pick up from an interactive prompt.
        self.loadFile(fh)
        self.selFile = fh
        if fh is not None:
            self.selFile.sigChanged.connect(self.selectedFileAltered)

    def loadFile(self, fh):
        if fh is None:
            self.ui.fileInfo.setCurrentFile(None)
            self.ui.dataViewWidget.setCurrentFile(None)
            self.ui.logWidget.set_records()
            self.ui.fileNameLabel.setText('')
        else:
            self.ui.fileNameLabel.setText(fh.name(relativeTo=self.baseDir))
            self.tabChanged()

    def tabChanged(self, n=None):
        if n is None:
            n = self.ui.fileDisplayTabs.currentIndex()
        fh = self.selectedFile()
        if n == 0:
            self.ui.fileInfo.setCurrentFile(fh)
        elif n == 1:
            log_file = fh.nearestLogFile()
            if self._logFile == log_file:
                return
            self._logFile = log_file
            if log_file is None:
                self.ui.logWidget.set_records()
            elif log_file.shortName().lower() == 'log.json':
                self.ui.logWidget.set_records(*load_log_records(log_file))
            elif log_file.shortName().lower() == 'log.txt':
                self.ui.logWidget.set_records(*load_log_records_legacy(log_file))
            else:
                self.ui.logWidget.set_records()

        elif n == 2:
            self.ui.dataViewWidget.setCurrentFile(fh)

    def selectedFileAltered(self, name, change, args):
        if change in ['parent', 'renamed', 'moved'] and self.selFile is not None:
            self.ui.fileTreeWidget.select(self.selFile)  ## re-select file if it has moved.
            self.ui.fileNameLabel.setText(self.selFile.name(relativeTo=self.baseDir))
        if change == 'renamed' and self.selFile is not None:
            self.updateCellID(self.selFile, os.path.basename(args[0]))

    @staticmethod
    def _nextCellName(sliceDir):
        """Return the next free cell folder name in *sliceDir*: .01, .02, ..."""
        numbers = [int(m.group(1)) for m in (re.match(r"^\.(\d+)$", n) for n in os.listdir(sliceDir.name())) if m]
        return ".%02d" % (max(numbers, default=0) + 1)

    def updateCellID(self, handle, oldName):
        """After a Cell folder is renamed (e.g. cell_000 -> .01), refresh its ID if it was empty or
        still the autofilled value for the old name; an ID typed by hand is left alone."""
        try:
            if not handle.isDir() or handle.info().get('dirType') != 'Cell':
                return
            current = handle.info().get('ID', '')
            if current not in ('', None, metadata_export.autoCellID(handle, oldName)):
                return
            handle.setInfo(ID=metadata_export.autoCellID(handle))
            self.ui.fileInfo.setCurrentFile(None)  # force the info panel to show the new ID
            self.tabChanged()
        except Exception:
            logger.exception("Could not update cell ID after rename:")

    def quit(self):
        ## Silly: needed to prevent lockup on some systems.
        self.ui.fileTreeWidget.quit()
        self.ui.analysisWidget.quit()
        Module.quit(self)

    def currentDatabase(self):
        return self.ui.analysisWidget.currentDatabase()

    def dataModel(self):
        return self.ui.analysisWidget.currentDataModel()

    def analysisDbChanged(self):
        self.sigAnalysisDbChanged.emit()
