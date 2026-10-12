"""Background read-in and conversion workers.

The heavy lifting lives in plain functions so it can be exercised without a
running Qt event loop; the QThread subclasses below wrap them for the UI.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Signal

from .geometry_data import HAS_GEOMETRY
from .model_summary import FilterData, ModelSummary, build_model_summary
from .settings_model import ConversionSettings

LogFn = Callable[[str], None]


def resolve_input(path: str | Path) -> tuple[Path, Path | None]:
    """Return the .ifc file to read, extracting IFCZIP archives if needed."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(path)
    if source.suffix.lower() not in {".ifczip", ".zip"}:
        return source, None
    with zipfile.ZipFile(source) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".ifc") and not n.endswith("/")]
        if len(names) != 1:
            raise ValueError("IFCZIP must contain exactly one .ifc file")
        handle = tempfile.NamedTemporaryFile(suffix=".ifc", delete=False)
        with handle, archive.open(names[0]) as member:
            handle.write(member.read())
        temp = Path(handle.name)
    return temp, temp


def run_read_in(settings: ConversionSettings, log: LogFn) -> tuple[ModelSummary, FilterData]:
    """Open the IFC model and collect statistics and filter inventories."""
    if not settings.ifc_file:
        raise ValueError("No IFC file selected")
    import ifcopenshell

    source, cleanup = resolve_input(settings.ifc_file)
    try:
        log(f"Reading IFC model {Path(settings.ifc_file).name} ...")
        model = ifcopenshell.open(str(source))
        log(f"Schema: {model.schema}")
        summary, filter_data = build_model_summary(
            model,
            settings.ifc_file,
            geometry_requested=settings.has_geometry or settings.has_element_wireframe,
            properties_requested=settings.has_building_properties,
        )
        log(f"Discovered {len(filter_data.element_type_counts)} element types and "
            f"{len(filter_data.property_set_counts)} property sets.")
        return summary, filter_data
    finally:
        if cleanup is not None:
            cleanup.unlink(missing_ok=True)


PRODUCT_NAMESPACE = "https://w3id.org/product#"
OPM_PROPERTY = "https://w3id.org/opm#Property"


def _safe_name(name: str) -> str:
    """Match the converter's URI sanitising for property set names."""
    from urllib.parse import quote

    return quote(str(name).strip().replace(" ", "_"), safe="-._~")


def apply_element_filters(graph, selected_types: set[str] | None, selected_psets: set[str] | None,
                          props_level: int = 1) -> int:
    """Drop elements (and level 3 property nodes) not covered by selections.

    Returns the number of element subjects removed. Empty selections keep the
    graph unchanged only when the corresponding selection is ``None``. An
    empty set means the user deliberately unchecked every item.
    """
    from rdflib import RDF, URIRef

    removed = 0
    if selected_types is not None:
        allowed = {PRODUCT_NAMESPACE + name[3:] if name.lower().startswith("ifc") else name
                   for name in selected_types}
        doomed = [subject for subject in graph.subjects(RDF.type, URIRef("https://w3id.org/bot#Element"))
                  if not any(str(obj) in allowed for obj in graph.objects(subject, RDF.type))]
        for subject in doomed:
            graph.remove((subject, None, None))
            graph.remove((None, None, subject))
        removed = len(doomed)
    if selected_psets is not None and props_level == 3:
        keep = {_safe_name(name) for name in selected_psets}
        for node in list(graph.subjects(RDF.type, URIRef(OPM_PROPERTY))):
            uri = str(node)
            if any(name in uri for name in keep):
                continue
            graph.remove((node, None, None))
            graph.remove((None, None, node))
    return removed


def run_conversion(settings: ConversionSettings, log: LogFn,
                   selected_types: set[str] | None = None,
                   selected_psets: set[str] | None = None,
                   is_cancelled: Callable[[], bool] | None = None) -> str:
    """Convert the selected IFC model to the target RDF file. Returns the path."""
    from ifctolbd.config import ConversionProperties
    from ifctolbd.converter import IFCtoLBDConverter

    if not settings.ifc_file or not settings.rdf_target:
        raise ValueError("Select IFC and target files before conversion")
    if is_cancelled and is_cancelled():
        raise CancelledError()

    base_uri = settings.base_uri.strip() or "https://dot.dc.rwth-aachen.de/IFCtoLBDset#"
    log(f"Converting {Path(settings.ifc_file).name} to {Path(settings.rdf_target).name} ...")
    props = ConversionProperties(
        has_building_elements=settings.has_building_elements,
        has_separate_building_elements_model=settings.has_separate_building_elements_model,
        has_building_properties=settings.has_building_properties,
        has_separate_properties_model=settings.has_separate_properties_model,
        has_geolocation=settings.has_geolocation,
        has_geometry=settings.has_geometry,
        export_ifcowl=settings.export_ifcowl,
        has_units=settings.has_units,
        has_bounding_box_wkt=settings.has_bounding_box_wkt,
        has_hierarchical_naming=settings.has_hierarchical_naming,
        has_performance_boost=settings.has_performance_boost,
        has_non_lbd_element=settings.has_ifc_based_elements,
        has_interfaces=settings.has_interfaces,
        has_wireframe=settings.has_element_wireframe,
    )
    converter = IFCtoLBDConverter(base_uri, settings.props_level)
    converter.setSelected_types(selected_types)
    converter.setSelected_psets(selected_psets)
    graph = converter.convert(settings.ifc_file, props)
    converter.close()
    if is_cancelled and is_cancelled():
        raise CancelledError()

    if settings.has_geometry:
        from rdflib import URIRef

        geometry_count = sum(1 for _ in graph.triples((None, URIRef(HAS_GEOMETRY), None)))
        if geometry_count:
            log(f"Geometry: {geometry_count} element meshes written to the output.")
        else:
            log("Geometry was requested, but no geometry was generated. "
                "Check that the installed IfcOpenShell has geometry support and "
                "that the model contains shape representations.")
    else:
        log("Geometry output disabled (Geometry option is off in Settings).")

    if selected_types is not None:
        log(f"Element filters: {len(selected_types)} type(s) selected.")
    if selected_psets is not None:
        log(f"Property filters: {len(selected_psets)} property set(s) selected.")
    if is_cancelled and is_cancelled():
        raise CancelledError()

    target = Path(settings.rdf_target)
    if settings.export_as_icdd():
        log("ICDD package export is not supported by the Python converter. Writing Turtle instead.")
    if target.suffix.lower() == ".jsonld":
        graph.serialize(destination=str(target), format="json-ld")
    else:
        graph.serialize(destination=str(target), format="turtle")
    log(f"RDF output written to {target} ({len(graph)} triples).")
    return str(target)


class CancelledError(RuntimeError):
    pass


class ReadInWorker(QThread):
    log = Signal(str)
    stage = Signal(str)
    succeeded = Signal(object, object)  # ModelSummary, FilterData
    failed = Signal(str)

    def __init__(self, settings: ConversionSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings

    def run(self) -> None:
        try:
            self.stage.emit("Reading IFC model")
            summary, filter_data = run_read_in(self.settings, self.log.emit)
            self.succeeded.emit(summary, filter_data)
        except Exception as error:
            self.failed.emit(str(error))


class ConversionWorker(QThread):
    log = Signal(str)
    stage = Signal(str)
    succeeded = Signal(str)  # output path
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, settings: ConversionSettings,
                 selected_types: set[str] | None = None,
                 selected_psets: set[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.selected_types = None if selected_types is None else set(selected_types)
        self.selected_psets = None if selected_psets is None else set(selected_psets)
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            self.stage.emit("Converting IFC to LBD")
            path = run_conversion(self.settings, self.log.emit,
                                  self.selected_types, self.selected_psets,
                                  lambda: self._cancel_requested)
            self.succeeded.emit(path)
        except CancelledError:
            self.cancelled.emit()
        except Exception as error:
            self.failed.emit(str(error))
