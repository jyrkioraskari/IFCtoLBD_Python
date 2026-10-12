from __future__ import annotations

from dataclasses import dataclass, replace

DEFAULT_BASE_URI = "https://dot.dc.rwth-aachen.de/IFCtoLBDset#"

OUTPUT_FORMATS = ("Turtle TTL", "JSON-LD", "ICDD")


@dataclass(slots=True)
class ConversionSettings:
    """Python replica of the Java ``ConversionSettings`` record."""

    ifc_file: str | None = None
    rdf_target: str | None = None
    base_uri: str = DEFAULT_BASE_URI
    props_level: int = 1
    has_building_elements: bool = True
    has_separate_building_elements_model: bool = False
    has_building_properties: bool = True
    has_separate_properties_model: bool = False
    has_properties_blank_nodes: bool = False
    has_geolocation: bool = True
    has_geometry: bool = True
    export_ifcowl: bool = False
    has_performance_boost: bool = False
    has_bounding_box_wkt: bool = False
    has_interfaces: bool = False
    has_element_wireframe: bool = False
    has_units: bool = True
    has_hierarchical_naming: bool = True
    has_simple_properties: bool = False
    properties_as_property_sets: bool = False
    has_ifc_based_elements: bool = False
    create_trig: bool = False
    output_format: str = OUTPUT_FORMATS[0]

    # Keys mirror the Java Preferences names so settings travel between apps.
    PREFERENCE_KEYS = {
        "has_building_elements": "lbd_building_elements",
        "has_separate_building_elements_model": "lbd_building_elements_separate_file",
        "has_building_properties": "lbd_building_props",
        "has_separate_properties_model": "lbd_building_props_separate_file",
        "has_properties_blank_nodes": "lbd_building_props_blank_nodes",
        "base_uri": "lbd_props_base_url",
        "has_geometry": "lbd_boundinbox_elements",
        "has_interfaces": "lbd_boundinbox_interfaces",
        "has_bounding_box_wkt": "lbd_boundinbox_wkt",
        "has_element_wireframe": "lbd_element_wireframe",
        "export_ifcowl": "lbd_ifcOWL_elements",
        "has_performance_boost": "lbd_performance",
        "has_units": "lbd_createUnits",
        "has_geolocation": "lbd_geolocation",
        "has_hierarchical_naming": "lbd_hasHierarchicalNaming",
        "has_simple_properties": "lbd_hasSimpleProperties",
        "properties_as_property_sets": "lbd_propertiesAsPropertySets",
        "has_ifc_based_elements": "ifc_based_elements",
        "create_trig": "createTrig",
        "props_level": "lbd_props_level",
        "output_format": "desktop_output_format",
    }

    def export_as_jsonld(self) -> bool:
        return "json" in self.output_format.lower()

    def export_as_icdd(self) -> bool:
        return "ICDD" in self.output_format.upper()

    def selected_output_extension(self) -> str:
        if self.export_as_icdd():
            return ".icdd"
        return ".jsonld" if self.export_as_jsonld() else ".ttl"

    def with_output_format(self, output_format: str) -> "ConversionSettings":
        settings = replace(self, output_format=output_format)
        if settings.rdf_target:
            settings.rdf_target = retarget_extension(settings.rdf_target, settings.selected_output_extension())
        return settings

    def has_read_in_options_changed(self, previous: "ConversionSettings | None") -> bool:
        if previous is None:
            return True
        comparable = (
            "ifc_file", "base_uri", "props_level", "has_building_elements", "has_building_properties",
            "has_properties_blank_nodes", "has_geolocation", "has_geometry", "export_ifcowl",
            "has_performance_boost", "has_bounding_box_wkt", "has_interfaces", "has_element_wireframe",
            "has_units",
        )
        return any(getattr(self, name) != getattr(previous, name) for name in comparable)


def retarget_extension(path: str, extension: str) -> str:
    """Return ``path`` with its extension replaced, keeping any directory part."""
    directory, separator, name = path.rpartition("/")
    dot = name.rfind(".")
    if dot > 0:
        name = name[:dot]
    return f"{directory}{separator}{name}{extension}"


def default_target_path(ifc_path: str, output_format: str, target_directory: str | None = None) -> str:
    """Build the "<model>_LBD.<ext>" target path offered after input selection."""
    import os

    stem = os.path.splitext(os.path.basename(ifc_path))[0]
    directory = target_directory or os.path.dirname(ifc_path) or "."
    settings = ConversionSettings(output_format=output_format)
    return os.path.join(directory, f"{stem}_LBD{settings.selected_output_extension()}")
