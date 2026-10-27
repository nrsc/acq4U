"""Dialog asking the user to fill in required metadata before a notebook export."""
from acq4.util import Qt
from .FileInfoView import fieldTypes


class MissingMetadataDialog(Qt.QDialog):
    """Lists the required fields that are empty, grouped by Slice/Cell folder, using the same
    widgets (and dropdown presets) as the Data Manager's info panel.

    After exec_(), ``choice`` is "save" (write the entered values, then export), "export"
    (export without filling them in) or None (cancel).
    """

    def __init__(self, missing, manager, baseDir=None, parent=None):
        Qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Complete metadata before export")
        self.choice = None
        self.fields = []  # (handle, MetadataField)

        layout = Qt.QVBoxLayout(self)
        label = Qt.QLabel("These fields are usually filled in the joint notebook but are empty here. "
                          "Fill in what you can; values are saved to the folders' metadata.")
        label.setWordWrap(True)
        layout.addWidget(label)

        for handle, names in missing.items():
            title = handle.name(relativeTo=baseDir) if baseDir is not None else handle.shortName()
            box = Qt.QGroupBox("%s  (%s)" % (title, handle.info().get("dirType", "")))
            form = Qt.QFormLayout(box)
            suggested = manager.suggestedDirFields(handle)
            for name in names:
                opts = suggested.get(name, "string")
                if not isinstance(opts, (dict, tuple)):
                    opts = (opts,)
                field = fieldTypes[opts[0]](name=name, value=None, config=opts)
                form.addRow(name, field.widget)
                self.fields.append((handle, field))
            layout.addWidget(box)

        buttons = Qt.QDialogButtonBox()
        saveBtn = buttons.addButton("Save and export", Qt.QDialogButtonBox.AcceptRole)
        exportBtn = buttons.addButton("Export without saving", Qt.QDialogButtonBox.ActionRole)
        buttons.addButton(Qt.QDialogButtonBox.Cancel)
        saveBtn.clicked.connect(lambda: self._finish("save"))
        exportBtn.clicked.connect(lambda: self._finish("export"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _finish(self, choice):
        self.choice = choice
        self.accept()

    def save(self):
        """Write every non-empty entered value to its folder's metadata. Returns the number saved."""
        values = {}
        for handle, field in self.fields:
            value = field.getValue()
            if isinstance(value, str):
                value = value.strip()
            if value not in ("", None):
                values.setdefault(handle, {})[field.name] = value
        for handle, info in values.items():
            handle.setInfo(info)
        return sum(len(v) for v in values.values())
