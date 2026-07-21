from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ConversionProperties:
    """Python equivalent of the Java ``ConversionProperties`` bean."""

    has_building_elements: bool = True
    has_separate_building_elements_model: bool = False
    has_building_properties: bool = True
    has_separate_properties_model: bool = False
    has_geolocation: bool = False
    has_geometry: bool = False
    export_ifcowl: bool = True
    has_units: bool = False
    has_bounding_box_wkt: bool = False
    has_hierarchical_naming: bool = False
    has_performance_boost: bool = True
    has_non_lbd_element: bool = True
    has_interfaces: bool = False
    has_wireframe: bool = False

    # Java-compatible accessors keep existing JPype-oriented examples working.
    def _get(self, name: str) -> bool:
        return bool(getattr(self, name))

    def _set(self, name: str, value: bool) -> None:
        setattr(self, name, bool(value))


_JAVA_FIELDS = {
    "HasBuildingElements": "has_building_elements",
    "HasSeparateBuildingElementsModel": "has_separate_building_elements_model",
    "HasBuildingProperties": "has_building_properties",
    "HasSeparatePropertiesModel": "has_separate_properties_model",
    "HasGeolocation": "has_geolocation",
    "HasGeometry": "has_geometry",
    "ExportIfcOWL": "export_ifcowl",
    "HasUnits": "has_units",
    "HasBoundingBoxWKT": "has_bounding_box_wkt",
    "HasHierarchicalNaming": "has_hierarchical_naming",
    "HasPerformanceBoost": "has_performance_boost",
    "HasNonLBDElement": "has_non_lbd_element",
    "HasInterfaces": "has_interfaces",
    "HasWireframe": "has_wireframe",
}


def _install_java_accessors() -> None:
    def getter(field: str):
        return lambda self: self._get(field)

    def setter(field: str):
        return lambda self, value: self._set(field, value)

    for java_name, field in _JAVA_FIELDS.items():
        setattr(ConversionProperties, f"is{java_name}", getter(field))
        setattr(ConversionProperties, f"set{java_name}", setter(field))
        setattr(ConversionProperties, java_name[0].lower() + java_name[1:], getter(field))


_install_java_accessors()

