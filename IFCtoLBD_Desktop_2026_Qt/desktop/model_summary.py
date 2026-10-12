from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ModelSummary:
    """Python replica of the Java ``ModelSummary`` record."""

    schema: str = "Unknown"
    file_size: str = "0 B"
    element_count: int = 0
    mapped_element_count: int = 0
    property_set_type_count: int = 0
    property_set_occurrence_count: int = 0
    storey_count: int = 0
    space_count: int = 0
    geometry_status: str = "Not loaded (disabled)"
    major_types: str = "None detected"
    warnings: list[str] = field(default_factory=list)

    def collapsed_title(self) -> str:
        title = f"Model Summary  ·  {self.schema}"
        if self.element_count:
            title += f"  ·  {self.element_count} elements"
        if self.property_set_type_count:
            title += f"  ·  {self.property_set_type_count} property sets"
        return title


@dataclass(slots=True)
class FilterData:
    """Element type and property set inventories for the Filters card."""

    element_type_counts: dict[str, int] = field(default_factory=dict)
    property_set_counts: dict[str, int] = field(default_factory=dict)
    type_roots: dict[str, str] = field(default_factory=dict)

    def element_type_groups(self) -> list[tuple[str, list[tuple[str, int]]]]:
        """Group element types under their concrete IFC root type."""
        groups: dict[str, list[tuple[str, int]]] = {}
        for name, count in sorted(self.element_type_counts.items()):
            root = self.type_roots.get(name, name)
            groups.setdefault(root, []).append((name, count))
        return [(root, entries) for root, entries in sorted(groups.items())]


GENERIC_ROOTS = {"IfcElement", "IfcBuildingElement", "IfcProduct", "IfcObject",
                 "IfcObjectDefinition", "IfcRoot", "IfcCharacterizedObject"}


def _type_roots(model: object, type_names: set[str]) -> dict[str, str]:
    """Map declared entity types to their nearest non-generic IFC supertype."""
    roots: dict[str, str] = {}
    try:
        import ifcopenshell

        schema = ifcopenshell.ifcopenshell_wrapper.schema_by_name(str(model.schema))
    except Exception:
        return {name: name for name in type_names}
    for name in type_names:
        root = name
        try:
            entity = schema.declaration_by_name(name)
            while True:
                supertype = entity.supertype()
                if supertype is None:
                    break
                entity = supertype
                if entity.name() not in GENERIC_ROOTS:
                    root = entity.name()
        except Exception:
            root = name
        roots[name] = root
    return roots


def format_file_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def build_model_summary(model: object, ifc_path: str | Path,
                        geometry_requested: bool, properties_requested: bool) -> tuple[ModelSummary, FilterData]:
    """Summarize an open ifcopenshell model the way the Java desktop app does."""
    element_counts: Counter[str] = Counter()
    element_total = 0
    geometry_available = False
    try:
        elements = model.by_type("IfcElement")
    except RuntimeError:
        elements = []
    for entity in elements:
        element_total += 1
        element_counts[entity.is_a()] += 1
        if getattr(entity, "Representation", None):
            geometry_available = True

    def count(type_name: str) -> int:
        try:
            return len(model.by_type(type_name))
        except RuntimeError:
            return 0

    storey_count = count("IfcBuildingStorey")
    space_count = count("IfcSpace")

    property_set_counts: Counter[str] = Counter()
    try:
        relations = model.by_type("IfcRelDefinesByProperties")
    except RuntimeError:
        relations = []
    for relation in relations:
        definition = getattr(relation, "RelatingPropertyDefinition", None)
        if definition is None:
            continue
        name = getattr(definition, "Name", None) or definition.is_a()
        property_set_counts[str(name)] += len(getattr(relation, "RelatedObjects", ()) or ())

    schema = str(getattr(model, "schema", "Unknown"))
    file_size = format_file_size(Path(ifc_path).stat().st_size)

    type_roots = _type_roots(model, set(element_counts))
    root_counts: Counter[str] = Counter()
    for name, count in element_counts.items():
        root_counts[type_roots.get(name, name)] += count
    mapped_element_count = sum(root_counts.values())
    geometry_status = ("Not loaded (disabled)" if not geometry_requested
                       else "Available" if geometry_available else "Requested, unavailable")

    major_types = "  ·  ".join(
        f"{name} {count}" for name, count in
        sorted(root_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    ) or "None detected"

    warnings: list[str] = []
    if not schema or schema == "Unknown":
        warnings.append("The IFC schema could not be identified.")
    if element_total == 0:
        warnings.append("No IFC elements were detected.")
    if storey_count == 0:
        warnings.append("No building storeys were detected.")
    if space_count == 0:
        warnings.append("No spaces were detected.")
    if properties_requested and not property_set_counts:
        warnings.append("No property sets were detected.")
    if geometry_requested and not geometry_available:
        warnings.append("Geometry was requested but no geometry data was available.")

    summary = ModelSummary(
        schema=schema,
        file_size=file_size,
        element_count=element_total,
        mapped_element_count=mapped_element_count,
        property_set_type_count=len(property_set_counts),
        property_set_occurrence_count=sum(property_set_counts.values()),
        storey_count=storey_count,
        space_count=space_count,
        geometry_status=geometry_status,
        major_types=major_types,
        warnings=warnings,
    )
    filter_data = FilterData(
        element_type_counts=dict(element_counts),
        property_set_counts=dict(property_set_counts),
        type_roots=type_roots,
    )
    return summary, filter_data
