from desktop.settings_model import (
    OUTPUT_FORMATS, ConversionSettings, default_target_path, retarget_extension,
)


def test_output_extension_selection() -> None:
    settings = ConversionSettings()
    assert settings.output_format == "Turtle TTL"
    assert settings.selected_output_extension() == ".ttl"
    assert not settings.export_as_jsonld()
    assert not settings.export_as_icdd()

    json = ConversionSettings(output_format="JSON-LD")
    assert json.export_as_jsonld()
    assert json.selected_output_extension() == ".jsonld"

    icdd = ConversionSettings(output_format="ICDD")
    assert icdd.export_as_icdd()
    assert icdd.selected_output_extension() == ".icdd"
    assert len(OUTPUT_FORMATS) == 3


def test_retarget_extension() -> None:
    assert retarget_extension("/tmp/model_LBD.ttl", ".jsonld") == "/tmp/model_LBD.jsonld"
    assert retarget_extension("model_LBD", ".ttl") == "model_LBD.ttl"
    # Java strips at the last dot: the file name itself is replaced.
    assert retarget_extension("/tmp/a.b/model.ifc", ".ttl") == "/tmp/a.b/model.ttl"


def test_with_output_format_updates_target() -> None:
    settings = ConversionSettings(rdf_target="/tmp/house_LBD.ttl", output_format="Turtle TTL")
    changed = settings.with_output_format("JSON-LD")
    assert changed.rdf_target == "/tmp/house_LBD.jsonld"
    assert changed.output_format == "JSON-LD"


def test_default_target_path() -> None:
    path = default_target_path("/work/ifc/house.ifc", "Turtle TTL", "/work/out")
    assert path == "/work/out/house_LBD.ttl"
    path = default_target_path("house.ifc", "JSON-LD")
    assert path.endswith("house_LBD.jsonld")


def test_read_in_settings_change_detection() -> None:
    first = ConversionSettings(ifc_file="a.ifc", rdf_target="a.ttl")
    assert first.has_read_in_options_changed(None)
    assert not ConversionSettings(ifc_file="a.ifc").has_read_in_options_changed(
        ConversionSettings(ifc_file="a.ifc", rdf_target="a.ttl"))
    assert ConversionSettings(ifc_file="a.ifc", props_level=3).has_read_in_options_changed(
        ConversionSettings(ifc_file="a.ifc", props_level=1))
    # Export-only options do not trigger a read-in rerun.
    assert not ConversionSettings(ifc_file="a.ifc", has_separate_properties_model=True
                                  ).has_read_in_options_changed(ConversionSettings(ifc_file="a.ifc"))
