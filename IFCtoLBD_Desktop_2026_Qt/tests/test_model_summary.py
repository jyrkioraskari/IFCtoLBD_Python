from pathlib import Path

import ifcopenshell

from desktop.model_summary import build_model_summary, format_file_size
from desktop.settings_model import ConversionSettings

SAMPLE = Path(__file__).resolve().parents[2] / "examples" / "data" / "two_walls.ifc"


def test_format_file_size() -> None:
    assert format_file_size(500) == "500 B"
    assert format_file_size(2048) == "2.0 KB"
    assert format_file_size(5 * 1024 * 1024) == "5.0 MB"


def test_model_summary_two_walls() -> None:
    model = ifcopenshell.open(str(SAMPLE))
    settings = ConversionSettings()
    summary, filters = build_model_summary(model, SAMPLE,
                                           geometry_requested=False,
                                           properties_requested=True)
    assert summary.schema == "IFC2X3"
    assert summary.file_size.endswith(" KB")
    assert summary.element_count == 2
    assert summary.storey_count >= 1
    assert summary.geometry_status == "Not loaded (disabled)"
    assert "IfcWall" in summary.major_types
    assert filters.element_type_counts  # declared types, e.g. IfcWallStandardCase
    assert any("IfcWall" in name for name in filters.element_type_counts)
    groups = filters.element_type_groups()
    assert groups and all(name.startswith("Ifc") for name, _ in groups[0][1])
    assert "Model Summary" in summary.collapsed_title()
