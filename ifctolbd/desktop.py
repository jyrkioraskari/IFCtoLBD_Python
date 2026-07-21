"""Small native desktop front end replacing the JavaFX modules."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PySide6.QtWidgets import QApplication, QFileDialog, QFormLayout, QLineEdit, QPushButton, QWidget
except ImportError as exc:
    raise RuntimeError("The desktop application requires: pip install 'ifctolbd[desktop]'") from exc

from .converter import IFCtoLBDConverter


class ConverterWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("IFCtoLBD")
        layout = QFormLayout(self)
        self.source = QLineEdit()
        self.target = QLineEdit()
        source_button = QPushButton("Select IFC…")
        target_button = QPushButton("Select RDF output…")
        convert_button = QPushButton("Convert")
        source_button.clicked.connect(self._source)
        target_button.clicked.connect(self._target)
        convert_button.clicked.connect(self._convert)
        layout.addRow(self.source, source_button)
        layout.addRow(self.target, target_button)
        layout.addRow(convert_button)

    def _source(self) -> None:
        value, _ = QFileDialog.getOpenFileName(self, "IFC input", filter="IFC (*.ifc *.ifczip *.zip)")
        if value:
            self.source.setText(value)

    def _target(self) -> None:
        value, _ = QFileDialog.getSaveFileName(self, "RDF output", filter="Turtle (*.ttl);;JSON-LD (*.jsonld);;RDF/XML (*.rdf)")
        if value:
            self.target.setText(value)

    def _convert(self) -> None:
        IFCtoLBDConverter().convert_to_file(Path(self.source.text()), Path(self.target.text()))


def main() -> int:
    app = QApplication(sys.argv)
    window = ConverterWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

