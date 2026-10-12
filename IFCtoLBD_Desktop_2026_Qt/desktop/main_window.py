"""Main window: Qt/PySide6 replica of the JavaFX IFCtoLBD_Desktop_2026 shell."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QEvent, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QCloseEvent, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QFileDialog, QFrame, QGridLayout, QHeaderView, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QMenuBar, QPlainTextEdit,
    QProgressBar, QPushButton, QRadioButton, QScrollArea, QSplitter,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .command_line import build_command_line
from .geometry_data import load_meshes_from_output
from .geometry_preview import GeometryViewport, PYVISTA_AVAILABLE
from .settings_model import OUTPUT_FORMATS, ConversionSettings, default_target_path, retarget_extension
from .shacl_validator import ShapeValidationItem, load_default_shapes, parse_shape_items, validate_item
from .sparql_runner import DEFAULT_SPARQL_QUERY, run_sparql_query
from .workers import ConversionWorker, ReadInWorker

FILTER_STATE_ROLE = Qt.ItemDataRole.UserRole + 2


class FloatingCard(QFrame):
    """Draggable, collapsible card matching the JavaFX floating TitledPanes."""

    def __init__(self, title: str, parent: QWidget | None = None,
                 normal_height: int = 450) -> None:
        super().__init__(parent)
        self.setObjectName("floatingCard")
        self.setFixedWidth(560)
        self._normal_height = normal_height
        self._expanded = True
        self._drag_offset = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("floatingCardTitle")
        self.title_label.installEventFilter(self)
        self.collapse_button = QPushButton("▾")
        self.collapse_button.setObjectName("floatingCardCollapseButton")
        self.collapse_button.setFixedSize(28, 24)
        self.collapse_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.collapse_button.clicked.connect(self.toggle_expanded)
        header.addWidget(self.title_label, 1)
        header.addWidget(self.collapse_button)
        layout.addLayout(header)
        self.content = QWidget()
        layout.addWidget(self.content)

    def set_content_layout(self, layout) -> None:
        self.content.setLayout(layout)

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.content.setVisible(expanded)
        self.collapse_button.setText("▾" if expanded else "▸")
        self.setFixedHeight(self._normal_height if expanded else 42)
        if expanded:
            self.raise_()

    def toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded)

    def _move_from_global(self, global_position) -> None:
        parent = self.parentWidget()
        if parent is None or self._drag_offset is None:
            return
        parent_position = parent.mapFromGlobal(global_position.toPoint())
        self.move(parent_position - self._drag_offset)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.title_label:
            if (event.type() == QEvent.Type.MouseButtonPress
                    and event.button() == Qt.MouseButton.LeftButton):
                self.raise_()
                self._drag_offset = self.mapFromGlobal(event.globalPosition().toPoint())
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
                self._move_from_global(event.globalPosition())
                return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_offset = None
                return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.raise_()
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 32:
            self._drag_offset = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self._move_from_global(event.globalPosition())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class FunctionWorker(QThread):
    """Runs a callable off the UI thread and reports success or failure."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, function, parent=None) -> None:
        super().__init__(parent)
        self._function = function

    def run(self) -> None:
        try:
            self.succeeded.emit(self._function())
        except Exception as error:  # noqa: BLE001 - shown in the UI
            self.failed.emit(str(error))


class AboutDialog(QDialog):
    """Replica of the Java About stage: dark dialog that closes on click."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About IFCtoLBD Desktop")
        self.setFixedSize(560, 250)
        self.setStyleSheet("background-color: black;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("IFCtoLBD Desktop (Qt) — Python converter edition\n2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026")
        authors = QLabel(
            "Authors: Jyrki Oraskari, Mathias Bonduel, Kris McGlinn, Anna Wagner,\n"
            "Pieter Pauwels, Ville Kukkonen, Simon Steyskaland, Joel Lehtonen,\n"
            "Maxime Lefrançois, and Lewis John McGibbney.\n"
            "Thanks also to Vladimir Alexiev, Kathrin Dentler, and Lukas Kirner\n"
            "for their valuable comments."
        )
        for label in (title, authors):
            label.setStyleSheet("color: white; background: transparent;")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(title)
        layout.addWidget(authors)
        layout.addStretch(1)

    def mousePressEvent(self, _event) -> None:  # noqa: N802
        self.close()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("IFCtoLBD Desktop")
        self.resize(1120, 760)
        self.setMinimumSize(900, 640)

        self.prefs = QSettings("IFCtoLBD", "IFCtoLBD_Desktop_2026_Qt")
        self.settings = self._load_settings()

        self.read_in_settings: ConversionSettings | None = None
        self.read_in_worker: ReadInWorker | None = None
        self.conversion_worker: ConversionWorker | None = None
        self.validation_worker: FunctionWorker | None = None
        self.latest_output: str | None = None
        self._mesh_cache: dict[str, list] = {}
        self._last_conversion_had_geometry = False
        self.filter_data = None
        self.selected_types: set[str] = set()
        self.selected_psets: set[str] = set()
        self.shape_items: list[ShapeValidationItem] = []
        self._filter_pressed_states: dict[tuple[int, int], Qt.CheckState] = {}
        self._operation_started = 0.0

        self._build_menu()
        self._build_ui()
        self._apply_preferences_to_ui()
        self._update_workflow_availability()

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self._update_elapsed)

    # ------------------------------------------------------------------ UI

    def _build_menu(self) -> None:
        menu_bar: QMenuBar = self.menuBar()
        file_menu: QMenu = menu_bar.addMenu("File")
        quit_action = file_menu.addAction("Quit")
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        help_menu: QMenu = menu_bar.addMenu("Help")
        about_action = help_menu.addAction("About IFCtoLBD Desktop")
        about_action.triggered.connect(self._about)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        top = QFrame()
        top.setObjectName("topRegion")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(18, 12, 18, 8)
        title_box = QVBoxLayout()
        app_title = QLabel("IFCtoLBD Desktop")
        app_title.setObjectName("appTitle")
        app_subtitle = QLabel("Convert IFC models into Linked Building Data")
        app_subtitle.setObjectName("appSubtitle")
        title_box.addWidget(app_title)
        title_box.addWidget(app_subtitle)
        top_layout.addLayout(title_box)
        top_layout.addStretch(1)
        root_layout.addWidget(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplit")
        splitter.addWidget(self._build_left_rail())
        splitter.addWidget(self._build_workspace())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([390, 720])
        root_layout.addWidget(splitter, 1)

    def _build_left_rail(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("leftRail")
        rail.setMinimumWidth(380)
        rail.setMaximumWidth(430)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        workflow_title = QLabel("Workflow")
        workflow_title.setObjectName("sectionTitle")
        layout.addWidget(workflow_title)
        layout.addWidget(self._build_advanced_workflow_tab())

        layout.addWidget(self._build_status_card())

        log_title = QLabel("Conversion Log")
        log_title.setObjectName("sectionTitle")
        layout.addWidget(log_title)
        self.conversion_log = QPlainTextEdit()
        self.conversion_log.setReadOnly(True)
        self.conversion_log.setPlaceholderText("Read-in and conversion messages appear here.")
        self.conversion_log.setMinimumHeight(112)
        layout.addWidget(self.conversion_log, 1)
        return rail

    def _build_advanced_workflow_tab(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        self.read_ifc_button = QPushButton("1  Read IFC")
        self.read_ifc_button.setObjectName("workflowButtonCurrent")
        self.read_ifc_button.clicked.connect(self.select_ifc_file)
        self.ifc_label = QLabel("No IFC file selected")
        self.ifc_label.setObjectName("fileLabel")
        grid.addWidget(self.read_ifc_button, 0, 0)
        grid.addWidget(self.ifc_label, 0, 1)

        settings_button = QPushButton("2  Settings")
        settings_button.setObjectName("workflowButton")
        settings_button.clicked.connect(self.open_settings_workflow)
        grid.addWidget(settings_button, 1, 0)

        self.filters_button = QPushButton("3  Filters")
        self.filters_button.setObjectName("workflowButton")
        self.filters_button.setEnabled(False)
        self.filters_button.clicked.connect(self.open_filters_workflow)
        grid.addWidget(self.filters_button, 2, 0)

        self.target_button = QPushButton("4  Output")
        self.target_button.setObjectName("workflowButton")
        self.target_button.setEnabled(False)
        self.target_button.clicked.connect(self.select_target_file)
        self.target_edit = QLineEdit()
        self.target_edit.setPlaceholderText("Output LBD file path")
        self.target_edit.setText("Target path will be generated after input selection")
        self.target_edit.textChanged.connect(self._target_edit_changed)
        grid.addWidget(self.target_button, 3, 0)
        grid.addWidget(self.target_edit, 3, 1)

        self.run_button = QPushButton("5  Run")
        self.run_button.setObjectName("workflowButton")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.convert_ifc_to_rdf)
        self.output_combo = QComboBox()
        self.output_combo.addItems(OUTPUT_FORMATS)
        self.output_combo.setMinimumWidth(130)
        self.output_combo.currentTextChanged.connect(self._output_format_changed)
        grid.addWidget(self.run_button, 4, 0)
        grid.addWidget(self.output_combo, 4, 1)

        test_label = QLabel("6  Test")
        test_label.setObjectName("workflowStepLabel")
        test_box = QHBoxLayout()
        test_box.setSpacing(6)
        self.geometry_button = QPushButton("Geometry")
        self.geometry_button.setObjectName("workflowMiniButton")
        self.geometry_button.setEnabled(False)
        self.geometry_button.clicked.connect(self.test_geometry_workflow)
        self.validate_button = QPushButton("Validate")
        self.validate_button.setObjectName("workflowMiniButton")
        self.validate_button.setEnabled(False)
        self.validate_button.clicked.connect(self.validate_workflow)
        self.query_button = QPushButton("Query")
        self.query_button.setObjectName("workflowMiniButton")
        self.query_button.setEnabled(False)
        self.query_button.clicked.connect(self.query_workflow)
        for button in (self.geometry_button, self.validate_button, self.query_button):
            test_box.addWidget(button, 1)
        grid.addWidget(test_label, 5, 0)
        grid.addLayout(test_box, 5, 1)

        self.copy_command_button = QPushButton("7  Copy command line")
        self.copy_command_button.setObjectName("workflowButton")
        self.copy_command_button.setToolTip("The command line command to the clipboard")
        self.copy_command_button.clicked.connect(self.copy_command_line)
        grid.addWidget(self.copy_command_button, 6, 0, 1, 2)
        grid.setRowStretch(7, 1)
        return page

    def _build_status_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("workflowStatusCard")
        self.status_card = card
        card.hide()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(6)
        top_row = QHBoxLayout()
        self.workflow_status_label = QLabel("Ready")
        self.workflow_status_label.setObjectName("workflowStatusLabel")
        self.workflow_elapsed_label = QLabel("00:00")
        self.workflow_elapsed_label.setObjectName("workflowElapsedLabel")
        top_row.addWidget(self.workflow_status_label, 1)
        top_row.addWidget(self.workflow_elapsed_label)
        layout.addLayout(top_row)
        bottom_row = QHBoxLayout()
        self.workflow_progress = QProgressBar()
        self.workflow_progress.setObjectName("workflowProgress")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("workflowCancelButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_workflow)
        bottom_row.addWidget(self.workflow_progress, 1)
        bottom_row.addWidget(self.cancel_button)
        layout.addLayout(bottom_row)
        return card

    def _build_workspace(self) -> QWidget:
        self.workspace = QFrame()
        self.workspace.setObjectName("freeWorkspace")
        self.cards: dict[str, FloatingCard] = {
            "settings": self._build_settings_card(),
            "filters": self._build_filters_card(),
            "geometry": self._build_geometry_card(),
            "sparql": self._build_sparql_card(),
            "validate": self._build_validate_card(),
        }
        positions = {
            "settings": (14, 14),
            "filters": (14, 66),
            "geometry": (150, 118),
            "sparql": (42, 170),
            "validate": (70, 222),
        }
        for name, card in self.cards.items():
            card.move(*positions[name])
            card.set_expanded(False)
            card.show()
        return self.workspace

    def _build_settings_card(self) -> FloatingCard:
        card = FloatingCard("Settings", self.workspace, normal_height=520)
        outer = QVBoxLayout()
        outer.setSpacing(10)

        base_row = QHBoxLayout()
        base_label = QLabel("Base URI")
        base_label.setObjectName("fieldLabel")
        self.base_uri_edit = QLineEdit()
        self.base_uri_edit.setPlaceholderText("https://example.org/building#")
        self.base_uri_edit.setText(self.settings.base_uri)
        self.base_uri_edit.textChanged.connect(self._settings_changed)
        base_row.addWidget(base_label)
        base_row.addWidget(self.base_uri_edit, 1)
        outer.addLayout(base_row)

        self.toggle_widgets: dict[str, QCheckBox] = {}
        # geometry_interfaces maps onto has_interfaces in the converter.
        self._attribute_aliases = {"geometry_interfaces": "has_interfaces"}
        toggle_rows: dict[str, list[tuple[str, str, bool]]] = {            "Product / BOT": [
                ("has_building_elements", "Building elements", True),
                ("has_separate_building_elements_model", "Separate product file", False),
                ("has_geolocation", "Geolocation", True),
                ("has_hierarchical_naming", "Hierarchical URI names", True),
            ],
            "Properties / OPM": [
                ("has_building_properties", "Properties", True),
                ("properties_as_property_sets", "Properties as property sets", False),
                ("has_separate_properties_model", "Separate property file", False),
                ("has_properties_blank_nodes", "Blank nodes", False),
                ("has_units", "Units", True),
                ("has_simple_properties", "Simple properties", False),
            ],
            "Geometry": [
                ("has_geometry", "Geometry", True),
                ("geometry_interfaces", "Candidate interfaces (bounding boxes)", False),
                ("has_bounding_box_wkt", "Bounding boxes", False),
                ("has_element_wireframe", "Element wireframe", False),
            ],
            "IfcOWL and Export": [
                ("export_ifcowl", "ifcOWL links", False),
                ("has_performance_boost", "Performance mode", False),
                ("has_ifc_based_elements", "IFC based elements", False),
                ("create_trig", "TriG file", False),
            ],
        }
        level_group: QButtonGroup | None = None
        for module_title, rows in toggle_rows.items():
            module = QFrame()
            module.setObjectName("moduleCard")
            module_layout = QVBoxLayout(module)
            module_layout.setContentsMargins(10, 6, 10, 10)
            module_title_label = QLabel(module_title)
            module_title_label.setObjectName("moduleTitle")
            module_layout.addWidget(module_title_label)
            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(8)
            for index, (attribute, text, default) in enumerate(rows):
                toggle = QCheckBox(text)
                settings_attribute = self._attribute_aliases.get(attribute, attribute)
                toggle.setChecked(getattr(self.settings, settings_attribute, default))
                toggle.toggled.connect(self._settings_changed)
                self.toggle_widgets[attribute] = toggle
                grid.addWidget(toggle, index // 2, index % 2)
            if module_title == "Properties / OPM":
                level_row = QHBoxLayout()
                level_label = QLabel("Level")
                level_label.setObjectName("fieldLabel")
                level_group = QButtonGroup(self)
                self.level_buttons: list[QRadioButton] = []
                for level in (1, 2, 3):
                    radio = QRadioButton(str(level))
                    if self.settings.props_level == level:
                        radio.setChecked(True)
                    radio.toggled.connect(self._settings_changed)
                    level_group.addButton(radio, level)
                    level_row.addWidget(radio)
                    self.level_buttons.append(radio)
                level_row.addStretch(1)
                level_row.addWidget(self._hyperlink("PROPS", "https://github.com/w3c-lbd-cg/lbd/blob/gh-pages/presentations/props/presentation_LBDcall_20180312_final.pdf"))
                level_row.addWidget(self._hyperlink("OPM", "https://github.com/w3c-lbd-cg/opm"))
                grid.addLayout(level_row, len(rows) // 2 + 1, 0, 1, 2)
            module_layout.addLayout(grid)
            if module_title == "Product / BOT":
                module_layout.addWidget(self._hyperlink("Read more", "https://github.com/w3c-lbd-cg/product"))
            outer.addWidget(module)

        # Java behaviour: selecting ifcOWL links disables performance mode.
        self.toggle_widgets["export_ifcowl"].toggled.connect(self._ifcowl_selection_changed)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setLayout(outer)
        scroll.setWidget(inner)
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(scroll)
        card.set_content_layout(card_layout)
        return card

    def _build_filters_card(self) -> FloatingCard:
        card = FloatingCard("Filters", self.workspace, normal_height=360)
        layout = QGridLayout()
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(8)
        for column, (title, attribute) in enumerate((("Element Types", "types"), ("Property Sets", "psets"))):
            box = QVBoxLayout()
            box.setSpacing(8)
            box_title = QLabel(title)
            box_title.setObjectName("sectionTitle")
            tree = QTreeWidget()
            tree.setObjectName("filterTree")
            tree.setHeaderHidden(True)
            tree.setMinimumHeight(220)
            tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            tree.setToolTip("Click anywhere on a row to include or exclude it.")
            tree.itemPressed.connect(self._filter_item_pressed)
            tree.itemClicked.connect(self._filter_item_clicked)
            tree.itemChanged.connect(self._filters_tree_changed)
            box.addWidget(box_title)
            box.addWidget(tree, 1)
            controls = QHBoxLayout()
            select_all = QPushButton("Select all")
            select_none = QPushButton("Clear")
            for button in (select_all, select_none):
                button.setObjectName("secondaryButton")
            select_all.clicked.connect(
                lambda _checked=False, target=tree: self._set_filter_tree_state(target, Qt.CheckState.Checked)
            )
            select_none.clicked.connect(
                lambda _checked=False, target=tree: self._set_filter_tree_state(target, Qt.CheckState.Unchecked)
            )
            controls.addWidget(select_all)
            controls.addWidget(select_none)
            controls.addStretch(1)
            box.addLayout(controls)
            if attribute == "types":
                self.element_types_tree = tree
            else:
                self.property_sets_tree = tree
            layout.addLayout(box, 0, column)
        self.filters_status_label = QLabel("Read an IFC model to populate filters.")
        self.filters_status_label.setObjectName("filtersStatusLabel")
        layout.addWidget(self.filters_status_label, 1, 0, 1, 2)
        card.set_content_layout(layout)
        return card

    def _build_geometry_card(self) -> FloatingCard:
        card = FloatingCard("Geometry Preview", self.workspace, normal_height=450)
        self.geometry_viewport = GeometryViewport()
        self.geometry_viewport.clear("Convert with geometry enabled to preview the model.")
        self.export_obj_button = QPushButton("Export OBJ")
        self.export_obj_button.setObjectName("secondaryButton")
        self.export_obj_button.clicked.connect(self.export_merged_obj)
        footer = QHBoxLayout()
        backend = "PyVista/VTK" if PYVISTA_AVAILABLE else "software fallback"
        self.geometry_backend_label = QLabel(f"LBD OBJ Exporter rendering · {backend}")
        footer.addWidget(self.geometry_backend_label)
        footer.addStretch(1)
        footer.addWidget(self.export_obj_button)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.geometry_viewport, 1)
        layout.addLayout(footer)
        card.set_content_layout(layout)
        return card

    def _build_sparql_card(self) -> FloatingCard:
        card = FloatingCard("SPARQL Query", self.workspace, normal_height=520)
        layout = QVBoxLayout()
        layout.setSpacing(9)
        editor_title = QLabel("SPARQL Editor")
        editor_title.setObjectName("sectionTitle")
        self.sparql_editor = QPlainTextEdit()
        self.sparql_editor.setPlainText(DEFAULT_SPARQL_QUERY)
        run_row = QHBoxLayout()
        self.run_sparql_button = QPushButton("Run query")
        self.run_sparql_button.setObjectName("primaryButton")
        self.run_sparql_button.clicked.connect(self.run_sparql_query)
        self.sparql_status_label = QLabel("Runs against the latest generated RDF output.")
        self.sparql_status_label.setObjectName("queryStatusLabel")
        run_row.addWidget(self.run_sparql_button)
        run_row.addWidget(self.sparql_status_label, 1)
        results_title = QLabel("Results")
        results_title.setObjectName("sectionTitle")
        self.sparql_results = QTableWidget()
        self.sparql_results.setObjectName("sparqlResultsTable")
        self.sparql_results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sparql_results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.sparql_results.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.sparql_results.setAlternatingRowColors(True)
        self.sparql_results.setSortingEnabled(False)
        self.sparql_results.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.sparql_results.verticalHeader().setVisible(False)
        self.sparql_results.horizontalHeader().setHighlightSections(False)
        layout.addWidget(editor_title)
        layout.addWidget(self.sparql_editor, 1)
        layout.addLayout(run_row)
        layout.addWidget(results_title)
        layout.addWidget(self.sparql_results, 1)
        card.set_content_layout(layout)
        return card

    def _build_validate_card(self) -> FloatingCard:
        card = FloatingCard("Validate", self.workspace, normal_height=520)
        layout = QVBoxLayout()
        layout.setSpacing(9)
        load_row = QHBoxLayout()
        self.load_shacl_button = QPushButton("Load SHACL")
        self.load_shacl_button.setObjectName("primaryButton")
        self.load_shacl_button.clicked.connect(self.load_shacl_shapes)
        self.validate_status_label = QLabel("Loaded SHACL shapes are tested against the latest generated RDF output.")
        self.validate_status_label.setObjectName("validationSummaryLabel")
        self.validate_status_label.setWordWrap(True)
        load_row.addWidget(self.load_shacl_button)
        load_row.addWidget(self.validate_status_label, 1)
        shapes_title = QLabel("Validation results")
        shapes_title.setObjectName("sectionTitle")
        self.shacl_table = QTableWidget()
        self.shacl_table.setObjectName("validationResultsTable")
        self.shacl_table.setColumnCount(4)
        self.shacl_table.setHorizontalHeaderLabels(["Status", "Shape", "Target", "Details"])
        self.shacl_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.shacl_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.shacl_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.shacl_table.setAlternatingRowColors(True)
        self.shacl_table.verticalHeader().setVisible(False)
        self.shacl_table.horizontalHeader().setHighlightSections(False)
        self.shacl_table.setMinimumHeight(190)
        self.shacl_table.currentCellChanged.connect(self._show_validation_details)
        self.validation_details = QPlainTextEdit()
        self.validation_details.setObjectName("validationDetails")
        self.validation_details.setReadOnly(True)
        self.validation_details.setMinimumHeight(105)
        self.validation_details.setMaximumHeight(135)
        self.validation_details.setPlaceholderText("Select a validation row to see its full report.")
        restore_row = QHBoxLayout()
        restore_row.addStretch(1)
        restore_button = QPushButton("Restore defaults")
        restore_button.setObjectName("secondaryButton")
        restore_button.clicked.connect(self.restore_default_shacl_shapes)
        restore_row.addWidget(restore_button)
        layout.addLayout(load_row)
        layout.addWidget(shapes_title)
        layout.addWidget(self.shacl_table, 1)
        layout.addWidget(self.validation_details)
        layout.addLayout(restore_row)
        card.set_content_layout(layout)
        self._restore_shapes_list(load_default_shapes())
        return card

    def _hyperlink(self, text: str, url: str) -> QLabel:
        label = QLabel(f'<a href="{url}">{text}</a>')
        label.setObjectName("appHyperlink")
        label.setOpenExternalLinks(True)
        return label

    # ------------------------------------------------------------- actions

    def select_ifc_file(self) -> None:
        directory = self.prefs.value("ifc_work_directory", ".", str)
        path, selected = QFileDialog.getOpenFileName(
            self, "Read IFC",
            directory,
            "IFC documents (*.ifc *.ifcxml *.ifcjson *.xml *.json);;IFC zip documents (*.ifczip);;All Files (*)",
        )
        if not selected:
            return
        self.prefs.setValue("ifc_work_directory", str(Path(path).parent))
        self.settings.ifc_file = path
        self.ifc_label.setText(Path(path).name)
        target_directory = self.prefs.value("ifc_target_directory", str(Path(path).parent), str)
        if not Path(target_directory).is_dir():
            target_directory = str(Path(path).parent)
        self.settings.rdf_target = default_target_path(path, self.settings.output_format, target_directory)
        self._sync_target_edit()
        self.target_button.setEnabled(True)
        self.start_read_in()

    def select_target_file(self) -> None:
        suggested = self.settings.rdf_target or ""
        path, selected = QFileDialog.getSaveFileName(
            self, "Output LBD file", suggested,
            "Turtle files (*.ttl);;JSON-LD files (*.jsonld);;ICDD packages (*.icdd)",
        )
        if not selected:
            return
        self.prefs.setValue("ifc_target_directory", str(Path(path).parent))
        self.settings.rdf_target = path
        self._sync_target_edit()
        self._update_workflow_availability()

    def _sync_target_edit(self) -> None:
        self.target_edit.blockSignals(True)
        self.target_edit.setText(self.settings.rdf_target or "")
        self.target_edit.blockSignals(False)

    def _set_run_ready(self, ready: bool) -> None:
        """Make the conversion action unmistakable once read-in has finished."""
        self.run_button.setEnabled(ready)
        self.run_button.setDefault(ready)
        self.run_button.setObjectName("workflowRunButton" if ready else "workflowButton")
        if ready:
            self.read_ifc_button.setDefault(False)

        # Qt does not automatically re-evaluate object-name selectors after a
        # widget has been polished, so refresh just the two workflow buttons.
        for button in (self.read_ifc_button, self.run_button):
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _target_edit_changed(self, text: str) -> None:
        if text and "Target path will be generated" not in text:
            self.settings.rdf_target = text
            self._update_workflow_availability()

    def start_read_in(self) -> None:
        if self._operation_running():
            self.log("The previous read-in or conversion is still running.")
            return
        self._persist_settings(self.settings)
        self.settings = self.settings.with_output_format(self.output_format())
        self.read_in_settings = self.settings
        self._set_run_ready(False)
        self.reset_conversion_output()
        self.conversion_log.clear()
        self.geometry_viewport.clear("Convert with geometry enabled to preview the model.")
        self._begin_workflow("Starting IFC read-in")
        self.read_in_worker = ReadInWorker(self.settings)
        self.read_in_worker.log.connect(self.log)
        self.read_in_worker.stage.connect(self._workflow_stage)
        self.read_in_worker.succeeded.connect(self._read_in_done)
        self.read_in_worker.failed.connect(lambda message: self._workflow_failed("Read-in failed", message))
        self.read_in_worker.start()

    def _read_in_done(self, _summary, filter_data) -> None:
        self.filter_data = filter_data
        self.selected_types = set(filter_data.element_type_counts)
        self.selected_psets = set(filter_data.property_set_counts)
        self._populate_filters(filter_data)
        self.filters_button.setEnabled(True)
        self._set_run_ready(True)
        self._finish_workflow("Read-in ready", True)
        self.log("Read-in complete. Adjust filters and run the conversion.")

    def convert_ifc_to_rdf(self) -> None:
        self.settings = self.current_settings()
        if not self.settings.ifc_file or not self.settings.rdf_target:
            self.log("Select IFC and target files before conversion.")
            return
        if self.read_in_worker is None:
            self.log("Read-in has not started yet.")
            return
        if self.read_in_worker.isRunning():
            self.log("Read-in is still running. Start conversion after it finishes.")
            return
        if self.settings.has_read_in_options_changed(self.read_in_settings):
            self.log("Re-running initial read due to changed settings.")
            self.start_read_in()
            self.log("Start conversion after read-in finishes.")
            return
        if self.conversion_worker is not None and self.conversion_worker.isRunning():
            self.log("The last conversion is still running.")
            return

        self._persist_settings(self.settings)
        self.conversion_log.clear()
        self.latest_output = None
        self._update_workflow_availability()
        self._begin_workflow("Starting conversion")
        self._collect_filters_selection()
        self.conversion_worker = ConversionWorker(
            self.settings, set(self.selected_types), set(self.selected_psets))
        self.conversion_worker.log.connect(self.log)
        self.conversion_worker.stage.connect(self._workflow_stage)
        self.conversion_worker.succeeded.connect(self._conversion_done)
        self.conversion_worker.failed.connect(lambda message: self._workflow_failed("Conversion failed", message))
        self.conversion_worker.cancelled.connect(lambda: self._finish_workflow("Cancelled", False))
        self.conversion_worker.start()

    def _conversion_done(self, output_path: str) -> None:
        self.latest_output = output_path
        self._last_conversion_had_geometry = self.settings.has_geometry
        self._mesh_cache.pop(output_path, None)
        self._finish_workflow("Conversion complete", True)
        self._update_workflow_availability()
        self.log("RDF output written. Running SHACL validation automatically.")
        self._validate_shapes()
        self.geometry_viewport.clear("Open the Geometry preview (step 6) to view the model mesh.")
        if self._last_conversion_had_geometry:
            # Match the reference desktop's scheduled post-conversion preview,
            # and make the result immediately visible to the user.
            if self.cards["geometry"].is_expanded():
                self.cards["geometry"].set_expanded(False)
            self.test_geometry_workflow()

    # ----------------------------------------------------------- workflow UI

    def _begin_workflow(self, status: str) -> None:
        self._operation_started = time.monotonic()
        self.workflow_elapsed_label.setText("00:00")
        self.workflow_progress.setRange(0, 0)  # indeterminate while working
        self.cancel_button.setEnabled(True)
        self.workflow_status_label.setText(status)
        self.status_card.show()
        self.elapsed_timer.start()

    def _workflow_stage(self, stage: str) -> None:
        self.workflow_status_label.setText(stage)

    def _finish_workflow(self, status: str, successful: bool) -> None:
        self.elapsed_timer.stop()
        self.cancel_button.setEnabled(False)
        self.workflow_progress.setRange(0, 1)
        self.workflow_progress.setValue(1 if successful else 0)
        self.workflow_status_label.setText(status)
        self._operation_started = 0.0

    def _workflow_failed(self, status: str, message: str) -> None:
        self._finish_workflow(status, False)
        self.log(message)

    def _update_elapsed(self) -> None:
        elapsed = int(time.monotonic() - self._operation_started) if self._operation_started else 0
        self.workflow_elapsed_label.setText(f"{elapsed // 60:02d}:{elapsed % 60:02d}")

    def cancel_workflow(self) -> None:
        if self.conversion_worker is not None and self.conversion_worker.isRunning():
            self.conversion_worker.request_cancel()
            self.workflow_status_label.setText("Cancelling...")
        else:
            self._finish_workflow("Cancelled", False)

    def _operation_running(self) -> bool:
        return ((self.read_in_worker is not None and self.read_in_worker.isRunning())
                or (self.conversion_worker is not None and self.conversion_worker.isRunning()))

    def reset_conversion_output(self) -> None:
        self.latest_output = None
        self.geometry_button.setEnabled(False)
        self.validate_button.setEnabled(False)
        self.query_button.setEnabled(False)

    # --------------------------------------------------------------- cards

    def _toggle_card(self, card: FloatingCard) -> None:
        card.set_expanded(not card.is_expanded())

    def open_settings_workflow(self) -> None:
        self._toggle_card(self.cards["settings"])

    def open_filters_workflow(self) -> None:
        if not self.filters_button.isEnabled():
            self.log("Read an IFC file before opening Filters.")
            return
        self._toggle_card(self.cards["filters"])

    def test_geometry_workflow(self) -> None:
        if not self.geometry_button.isEnabled():
            self.log("Run a conversion before opening Geometry Preview.")
            return
        self._toggle_card(self.cards["geometry"])
        if not self.cards["geometry"].is_expanded() or not self.latest_output:
            return
        output = self.latest_output
        if output in self._mesh_cache:
            self.geometry_viewport.set_meshes(self._mesh_cache[output])
            return
        self.geometry_viewport.clear("Loading geometry...")

        def load():
            return load_meshes_from_output(output)

        self.geometry_loader = FunctionWorker(load)
        self.geometry_loader.succeeded.connect(lambda meshes: self._geometry_loaded(output, meshes))
        self.geometry_loader.failed.connect(self._geometry_load_failed)
        self.geometry_loader.start()

    def _geometry_loaded(self, output: str, meshes: list) -> None:
        if meshes:
            self._mesh_cache[output] = meshes
            self.geometry_viewport.set_meshes(meshes)
            face_count = sum(len(mesh.faces) for mesh in meshes)
            backend = getattr(self.geometry_viewport, "active_backend_name", "unknown renderer")
            self.geometry_backend_label.setText(f"LBD OBJ Exporter rendering · {backend}")
            self.log(
                f"Geometry preview: showing {len(meshes)} objects / {face_count} faces "
                f"with {backend}."
            )
            return
        if not self._last_conversion_had_geometry:
            message = ("The last conversion ran with the Geometry option disabled.\n"
                       "Enable Geometry in Settings (step 2), press Run (step 5),\n"
                       "then reopen this preview.")
        else:
            message = ("The RDF output contains no OBJ geometry although geometry\n"
                       "was requested. The installed IfcOpenShell may lack geometry\n"
                       "support: check the conversion log for details.")
        self.geometry_viewport.clear(message)
        self.log("Geometry preview: " + message.replace("\n", " "))

    def _geometry_load_failed(self, message: str) -> None:
        text = f"Geometry preview failed: {message}"
        self.geometry_viewport.clear(text)
        self.log(text)

    def export_merged_obj(self) -> None:
        """LBD_OBJ_Exporter feature: write all previewed geometry as one OBJ."""
        from .obj_exporter import export_merged_obj as write_merged_obj

        meshes = self._mesh_cache.get(self.latest_output or "", [])
        if not meshes:
            self.log("Open the geometry preview with meshes before exporting OBJ.")
            return
        suggested = str(Path(self.settings.rdf_target or "lbd_model").with_suffix(".obj"))
        path, selected = QFileDialog.getSaveFileName(
            self, "Export merged OBJ", suggested, "Wavefront OBJ (*.obj);;All Files (*)")
        if not selected:
            return
        try:
            write_merged_obj((mesh.obj_text for mesh in meshes), path)
        except OSError as error:
            self.log(f"OBJ export failed: {error}")
            return
        self.log(f"Exported {len(meshes)} elements to {path} as merged OBJ.")

    def query_workflow(self) -> None:
        if not self.query_button.isEnabled():
            self.log("Generate an RDF output before opening SPARQL Query.")
            return
        self._toggle_card(self.cards["sparql"])

    def validate_workflow(self) -> None:
        if not self.validate_button.isEnabled():
            self.log("Generate an RDF output before opening Validate.")
            return
        self._toggle_card(self.cards["validate"])
        self._validate_shapes()

    # --------------------------------------------------------------- SPARQL

    def run_sparql_query(self) -> None:
        if not self.query_button.isEnabled():
            self._clear_sparql_results("Generate an RDF output to run SPARQL queries.")
            return
        query_text = self.sparql_editor.toPlainText()
        if not query_text.strip():
            self._clear_sparql_results("Enter a SPARQL query.")
            return
        self.run_sparql_button.setEnabled(False)
        self._clear_sparql_results("Running query…")
        output = self.latest_output
        self.sparql_worker = FunctionWorker(lambda: run_sparql_query(output, query_text))
        self.sparql_worker.succeeded.connect(self._sparql_done)
        self.sparql_worker.failed.connect(self._sparql_failed)
        self.sparql_worker.start()

    def _sparql_done(self, result) -> None:
        self.sparql_results.setSortingEnabled(False)
        self.sparql_results.clear()
        self.sparql_results.setColumnCount(len(result.columns))
        self.sparql_results.setRowCount(len(result.rows))
        self.sparql_results.setHorizontalHeaderLabels(list(result.columns))
        for row_index, row in enumerate(result.rows):
            for column_index, value in enumerate(row):
                display = " ".join(value.splitlines())
                if len(display) > 500:
                    display = display[:240] + " … " + display[-240:]
                item = QTableWidgetItem(display)
                item.setToolTip(value if len(value) <= 2_000 else value[:2_000] + "…")
                self.sparql_results.setItem(row_index, column_index, item)

        header = self.sparql_results.horizontalHeader()
        for column in range(len(result.columns)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            sample_width = max(
                [len(result.columns[column])]
                + [len(row[column]) for row in result.rows[:50]]
            )
            self.sparql_results.setColumnWidth(column, max(90, min(280, sample_width * 7 + 24)))
        if result.columns:
            header.setStretchLastSection(True)
        self.sparql_results.setSortingEnabled(bool(result.rows))
        self.sparql_status_label.setText(result.message or "Query completed with no tabular results.")
        self.run_sparql_button.setEnabled(True)

    def _sparql_failed(self, message: str) -> None:
        self._clear_sparql_results("SPARQL query failed: " + message)
        self.run_sparql_button.setEnabled(True)

    def _clear_sparql_results(self, status: str) -> None:
        self.sparql_results.clear()
        self.sparql_results.setRowCount(0)
        self.sparql_results.setColumnCount(0)
        self.sparql_status_label.setText(status)

    # ---------------------------------------------------------------- SHACL

    def load_shacl_shapes(self) -> None:
        path, selected = QFileDialog.getOpenFileName(
            self, "Load SHACL shapes", "", "Turtle files (*.ttl);;All Files (*)")
        if not selected:
            return
        try:
            items = parse_shape_items(path)
        except Exception as error:  # noqa: BLE001
            self.validate_status_label.setText(f"Could not load shapes: {error}")
            return
        self._restore_shapes_list(items, keep_defaults=False)
        self.validate_status_label.setText(f"Loaded {len(items)} shapes from {Path(path).name}.")
        self._validate_shapes()

    def restore_default_shacl_shapes(self) -> None:
        self._restore_shapes_list(load_default_shapes())
        self.validate_status_label.setText("Restored the default SHACL ruleset.")
        if self.validate_button.isEnabled():
            self._validate_shapes()

    def _restore_shapes_list(self, items: list[ShapeValidationItem], keep_defaults: bool = True) -> None:
        if keep_defaults and self.shape_items:
            combined = {item.shape_node: item for item in self.shape_items}
            for item in items:
                combined.setdefault(item.shape_node, item)
            items = list(combined.values())
        self.shape_items = items
        self.shacl_table.clearContents()
        self.shacl_table.setRowCount(len(items))
        self._paint_shape_rows()

    def _validate_shapes(self) -> None:
        if not self.latest_output:
            self.validate_status_label.setText("Generate an RDF output to validate loaded SHACL shapes.")
            return
        if self.validation_worker is not None and self.validation_worker.isRunning():
            self._set_validation_summary("Validation is already running…", "running")
            return
        output = self.latest_output
        for item in self.shape_items:
            item.conforms = None
            item.message = "Validation in progress…"
        self._paint_shape_rows()
        self._set_validation_summary("Validating shapes against the RDF output…", "running")

        def validate_all():
            return [validate_item(item, output) for item in self.shape_items]

        self.validation_worker = FunctionWorker(validate_all)
        self.validation_worker.succeeded.connect(self._validation_done)
        self.validation_worker.failed.connect(self._validation_failed)
        self.validation_worker.start()

    def _validation_failed(self, message: str) -> None:
        detail = "Validation could not run: " + message
        for item in self.shape_items:
            if item.conforms is None:
                item.message = detail
        self._paint_shape_rows()
        self._set_validation_summary(detail, "error")
        if self.shape_items:
            self.shacl_table.clearSelection()
            self._show_validation_details(0, 0, -1, -1)

    def _validation_done(self, results: list) -> None:
        for item, (conforms, message) in zip(self.shape_items, results):
            item.conforms = conforms
            item.message = message
        self._paint_shape_rows()
        passed = sum(item.conforms is True for item in self.shape_items)
        failed = sum(item.conforms is False for item in self.shape_items)
        errors = len(self.shape_items) - passed - failed
        state = "fail" if failed else "error" if errors else "pass"
        self._set_validation_summary(
            f"{passed} passed  ·  {failed} failed  ·  {errors} errors",
            state,
        )
        first_problem = next(
            (index for index, item in enumerate(self.shape_items) if item.conforms is not True),
            0 if self.shape_items else -1,
        )
        if first_problem >= 0:
            # Keep the status color visible on initial presentation. The
            # corresponding failure report is shown below without applying
            # Qt's selection overlay to the red failure row.
            self.shacl_table.clearSelection()
            self._show_validation_details(first_problem, 0, -1, -1)

    def _paint_shape_rows(self) -> None:
        for row, item in enumerate(self.shape_items):
            if item.conforms is True:
                status, detail = "✓ PASS", "Conforms"
                background, foreground = "#dcfce7", "#166534"
            elif item.conforms is False:
                violations = max(1, item.message.count("Constraint Violation"))
                status, detail = "✕ FAIL", f"{violations} violation(s)"
                background, foreground = "#fee2e2", "#991b1b"
            else:
                is_running = item.message == "Validation in progress…"
                is_ready = item.message == "Ready to validate"
                is_error = not (is_running or is_ready)
                status = "… RUNNING" if is_running else "! ERROR" if is_error else "○ READY"
                detail = item.message.splitlines()[0]
                background = "#fef3c7" if is_error else "#dbeafe" if is_running else "#f1f5f9"
                foreground = "#92400e" if is_error else "#1e40af" if is_running else "#64748b"

            target = item.target_class.rsplit("#", 1)[-1].rsplit("/", 1)[-1] or "—"
            values = (status, item.display_name, target, detail)
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(value)
                table_item.setToolTip(item.message if column in (0, 3) else str(item.shape_node))
                table_item.setBackground(QColor(background))
                table_item.setForeground(QColor(foreground))
                if column == 0:
                    font = table_item.font()
                    font.setBold(True)
                    table_item.setFont(font)
                    table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.shacl_table.setItem(row, column, table_item)

        header = self.shacl_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.shacl_table.setColumnWidth(0, 82)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.shacl_table.setColumnWidth(1, 145)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.shacl_table.setColumnWidth(2, 100)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.shacl_table.resizeRowsToContents()

    def _show_validation_details(self, row: int, _column: int, _old_row: int, _old_column: int) -> None:
        if 0 <= row < len(self.shape_items):
            item = self.shape_items[row]
            self.validation_details.setPlainText(
                f"{item.display_name}\n{item.shape_node}\n\n{item.message}"
            )

    def _set_validation_summary(self, text: str, state: str) -> None:
        colors = {
            "pass": ("#dcfce7", "#166534", "#86efac"),
            "fail": ("#fee2e2", "#991b1b", "#fca5a5"),
            "error": ("#fef3c7", "#92400e", "#fcd34d"),
            "running": ("#dbeafe", "#1e40af", "#93c5fd"),
        }
        background, foreground, border = colors.get(state, colors["running"])
        self.validate_status_label.setText(text)
        self.validate_status_label.setStyleSheet(
            f"background:{background};color:{foreground};border:1px solid {border};"
            "border-radius:7px;padding:6px 8px;font-weight:700;"
        )

    # -------------------------------------------------------------- filters

    def _populate_filters(self, filter_data) -> None:
        self.element_types_tree.blockSignals(True)
        self.property_sets_tree.blockSignals(True)
        self.element_types_tree.clear()
        self.property_sets_tree.clear()
        for root_name, entries in filter_data.element_type_groups():
            root_text = f"{root_name} ({sum(count for _, count in entries)})"
            root = QTreeWidgetItem([root_text])
            root.setData(0, Qt.ItemDataRole.UserRole + 1, root_text)
            root.setData(0, FILTER_STATE_ROLE, Qt.CheckState.Checked)
            self.element_types_tree.addTopLevelItem(root)
            for name, count in entries:
                child_text = f"{name} ({count})"
                child = QTreeWidgetItem([child_text])
                child.setData(0, Qt.ItemDataRole.UserRole, name)
                child.setData(0, Qt.ItemDataRole.UserRole + 1, child_text)
                child.setData(0, FILTER_STATE_ROLE, Qt.CheckState.Checked)
                root.addChild(child)
        for name, count in sorted(filter_data.property_set_counts.items()):
            item_text = f"{name} ({count})"
            item = QTreeWidgetItem([item_text])
            item.setData(0, Qt.ItemDataRole.UserRole, name)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, item_text)
            item.setData(0, FILTER_STATE_ROLE, Qt.CheckState.Checked)
            self.property_sets_tree.addTopLevelItem(item)
        self.element_types_tree.expandAll()
        self.element_types_tree.blockSignals(False)
        self.property_sets_tree.blockSignals(False)
        self._collect_filters_selection()

    def _checked_values(self, tree: QTreeWidget, strip_counts: bool) -> set[str]:
        values: set[str] = set()
        def walk(item):
            text = item.text(0)
            if self._filter_state(item) == Qt.CheckState.Checked:
                value = item.data(0, Qt.ItemDataRole.UserRole) or text
                if strip_counts and " (" in value and value.endswith(")"):
                    value = value[:value.rfind(" (")]
                if not item.childCount() or not strip_counts:
                    values.add(value)
            for index in range(item.childCount()):
                walk(item.child(index))
        for index in range(tree.topLevelItemCount()):
            walk(tree.topLevelItem(index))
        return values

    def _collect_filters_selection(self) -> None:
        self.selected_types = self._checked_values(self.element_types_tree, strip_counts=True)
        self.selected_psets = self._checked_values(self.property_sets_tree, strip_counts=True)
        if self.filter_data is not None:
            self.filters_status_label.setText(
                f"Included: {len(self.selected_types)} of {len(self.filter_data.element_type_counts)} element types"
                f"  ·  {len(self.selected_psets)} of {len(self.filter_data.property_set_counts)} property sets"
            )
        self._paint_filter_selections()

    def _paint_filter_selections(self) -> None:
        """Make inclusion state obvious beyond Qt's small native checkbox."""
        palette = {
            Qt.CheckState.Checked: ("✓", "#e4f0ff", "#174ea6"),
            Qt.CheckState.PartiallyChecked: ("–", "#fff4d6", "#8a5a00"),
            Qt.CheckState.Unchecked: ("○", "#f8fafc", "#7a8699"),
        }
        for tree in (self.element_types_tree, self.property_sets_tree):
            tree.blockSignals(True)

            def paint(item: QTreeWidgetItem) -> None:
                state = self._filter_state(item)
                symbol, background, foreground = palette[state]
                base_text = item.data(0, Qt.ItemDataRole.UserRole + 1) or item.text(0)
                item.setText(0, f"{symbol}  {base_text}")
                item.setBackground(0, QBrush(QColor(background)))
                item.setForeground(0, QBrush(QColor(foreground)))
                font = item.font(0)
                font.setBold(state != Qt.CheckState.Unchecked)
                item.setFont(0, font)
                for child_index in range(item.childCount()):
                    paint(item.child(child_index))

            for index in range(tree.topLevelItemCount()):
                paint(tree.topLevelItem(index))
            tree.blockSignals(False)

    def _filters_tree_changed(self, _item, _column) -> None:
        self._collect_filters_selection()

    @staticmethod
    def _filter_state(item: QTreeWidgetItem) -> Qt.CheckState:
        value = item.data(0, FILTER_STATE_ROLE)
        return value if isinstance(value, Qt.CheckState) else Qt.CheckState(value)

    def _filter_item_pressed(self, item: QTreeWidgetItem, column: int) -> None:
        self._filter_pressed_states[(id(item), column)] = self._filter_state(item)

    def _filter_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Make the complete tree row act as the checkbox hit target.

        Qt toggles only when the small indicator itself is clicked. If Qt has
        already changed the state, preserve it; otherwise the click occurred
        on the row label and is handled here.
        """
        key = (id(item), column)
        current = self._filter_state(item)
        previous = self._filter_pressed_states.pop(key, current)
        if current != previous:
            return
        target = (Qt.CheckState.Unchecked if previous == Qt.CheckState.Checked
                  else Qt.CheckState.Checked)
        tree = item.treeWidget()
        tree.blockSignals(True)

        def set_item(current: QTreeWidgetItem) -> None:
            current.setData(0, FILTER_STATE_ROLE, target)
            for child_index in range(current.childCount()):
                set_item(current.child(child_index))

        set_item(item)
        parent = item.parent()
        while parent is not None:
            child_states = [self._filter_state(parent.child(index))
                            for index in range(parent.childCount())]
            parent_state = (Qt.CheckState.Checked
                            if all(state == Qt.CheckState.Checked for state in child_states)
                            else Qt.CheckState.Unchecked
                            if all(state == Qt.CheckState.Unchecked for state in child_states)
                            else Qt.CheckState.PartiallyChecked)
            parent.setData(0, FILTER_STATE_ROLE, parent_state)
            parent = parent.parent()
        tree.blockSignals(False)
        self._collect_filters_selection()

    def _set_filter_tree_state(self, tree: QTreeWidget, state: Qt.CheckState) -> None:
        tree.blockSignals(True)

        def set_item(item: QTreeWidgetItem) -> None:
            item.setData(0, FILTER_STATE_ROLE, state)
            for child_index in range(item.childCount()):
                set_item(item.child(child_index))

        for index in range(tree.topLevelItemCount()):
            set_item(tree.topLevelItem(index))
        tree.blockSignals(False)
        self._collect_filters_selection()

    # ------------------------------------------------------------- settings

    def _ifcowl_selection_changed(self, checked: bool) -> None:
        performance = self.toggle_widgets["has_performance_boost"]
        performance.setEnabled(not checked)
        if checked:
            performance.setChecked(False)

    def _settings_changed(self) -> None:
        for attribute, toggle in self.toggle_widgets.items():
            real = self._attribute_aliases.get(attribute, attribute)
            setattr(self.settings, real, toggle.isChecked())
        for level, radio in enumerate(self.level_buttons, start=1):
            if radio.isChecked():
                self.settings.props_level = level
        self.settings.base_uri = self.base_uri_edit.text()

    def output_format(self) -> str:
        return self.output_combo.currentText()

    def _output_format_changed(self, text: str) -> None:
        self.settings.output_format = text
        if self.settings.rdf_target and "Target path will be generated" not in self.settings.rdf_target:
            self.settings = self.settings.with_output_format(text)
            self._sync_target_edit()

    def current_settings(self) -> ConversionSettings:
        self._settings_changed()
        settings = self.settings.with_output_format(self.output_format())
        return settings

    def copy_command_line(self) -> None:
        settings = self.current_settings()
        if not settings.ifc_file or not settings.rdf_target:
            self.log("Select IFC and target files before copying the command line.")
            return
        try:
            command = build_command_line(settings, sorted(self.selected_types), sorted(self.selected_psets))
        except ValueError as error:
            self.log(str(error))
            return
        QGuiApplication.clipboard().setText(command)
        self.log("Command line copied to the clipboard.")

    # ------------------------------------------------------------ plumbing

    def _apply_preferences_to_ui(self) -> None:
        self._sync_target_edit()
        for attribute, toggle in self.toggle_widgets.items():
            toggle.setChecked(getattr(self.settings, self._attribute_aliases.get(attribute, attribute)))
        for level, radio in enumerate(self.level_buttons, start=1):
            radio.setChecked(level == self.settings.props_level)
        self.output_combo.setCurrentText(self.settings.output_format)

    def _load_settings(self) -> ConversionSettings:
        settings = ConversionSettings()
        for attribute, key in ConversionSettings.PREFERENCE_KEYS.items():
            value = self.prefs.value(key)
            if value is None:
                continue
            if isinstance(getattr(settings, attribute), bool):
                setattr(settings, attribute, value in (True, "true"))
            elif isinstance(getattr(settings, attribute), int):
                setattr(settings, attribute, int(value))
            else:
                setattr(settings, attribute, str(value))
        return settings

    def _persist_settings(self, settings: ConversionSettings) -> None:
        for attribute, key in ConversionSettings.PREFERENCE_KEYS.items():
            self.prefs.setValue(key, getattr(settings, attribute))

    def _update_workflow_availability(self) -> None:
        output_ready = self.latest_output is not None
        self.geometry_button.setEnabled(output_ready)
        self.validate_button.setEnabled(output_ready)
        self.query_button.setEnabled(output_ready)

    def log(self, message: str) -> None:
        self.conversion_log.appendPlainText(message)

    def _about(self) -> None:
        AboutDialog(self).exec()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        for worker in (self.read_in_worker, self.conversion_worker, self.validation_worker):
            if worker is not None and worker.isRunning():
                worker.wait(2000)
        close_viewport = getattr(self.geometry_viewport, "close", None)
        if callable(close_viewport):
            close_viewport()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    import sys

    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("IFCtoLBD Desktop")
    stylesheet_path = Path(__file__).resolve().parent / "resources" / "app.qss"
    if stylesheet_path.is_file():
        app.setStyleSheet(stylesheet_path.read_text(encoding="utf-8"))
    window = MainWindow()
    window.show()
    return app.exec()
