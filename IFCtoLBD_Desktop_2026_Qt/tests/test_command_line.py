import pytest

from desktop.command_line import build_command_line
from desktop.settings_model import ConversionSettings


def test_basic_command_line() -> None:
    settings = ConversionSettings(
        ifc_file="/models/house.ifc",
        rdf_target="/models/house_LBD.ttl",
        base_uri="https://example.org/building#",
        props_level=2,
        has_geometry=True,
    )
    command = build_command_line(settings)
    assert command.startswith("ifctolbd '/models/house.ifc' '/models/house_LBD.ttl'")
    assert "--base-uri 'https://example.org/building#'" in command
    assert "--level 2" in command
    assert "--geometry" in command


def test_disabled_flags_are_omitted() -> None:
    settings = ConversionSettings(
        ifc_file="a.ifc",
        rdf_target="a.ttl",
        has_building_properties=False,
        export_ifcowl=False,
        has_geometry=False,
        has_geolocation=False,
        has_units=False,
    )
    command = build_command_line(settings)
    assert "--no-properties" in command
    assert "--no-ifcowl" in command
    assert "--geometry" not in command
    assert "--geolocation" not in command
    assert "--units" not in command


def test_icdd_returns_comment() -> None:
    settings = ConversionSettings(ifc_file="a.ifc", rdf_target="a.icdd",
                                  output_format="ICDD")
    assert build_command_line(settings).startswith("# ICDD package export")


def test_missing_files_raise() -> None:
    with pytest.raises(ValueError):
        build_command_line(ConversionSettings())
