from pathlib import Path

from desktop.obj_exporter import (
    DEFAULT_MATERIAL_COLOR, display_color, export_merged_obj, is_opaque_type,
    is_window_type, local_type_name, merge_obj_documents, parse_alpha,
    parse_kd_color, row_opacity,
)


def test_parse_kd_color() -> None:
    assert parse_kd_color("#ff8000") == (255, 128, 0)
    assert parse_kd_color("0.5 0.25 0.0") == (128, 64, 0)
    assert parse_kd_color("255, 128, 0") == (255, 128, 0)
    assert parse_kd_color("not a color") is None
    assert parse_kd_color("") is None


def test_parse_alpha() -> None:
    assert parse_alpha("0.5") == 0.5
    assert parse_alpha("2") == 1.0
    assert parse_alpha("-1") == 0.0
    assert parse_alpha("junk") == 1.0
    assert parse_alpha("") == 1.0


def test_type_classification() -> None:
    assert is_window_type("Window")
    assert is_window_type("Window-2x")
    assert not is_window_type("Wall")
    assert is_opaque_type("Wall")
    assert is_opaque_type("WallStandardCase")
    assert is_opaque_type("Slab")
    assert is_opaque_type("Roof")
    assert not is_opaque_type("Space")
    assert local_type_name("https://w3id.org/product#Door") == "Door"
    assert display_color("WallStandardCase") == (211, 205, 196)
    assert display_color("SomethingElse") == DEFAULT_MATERIAL_COLOR


def test_row_opacity_rules() -> None:
    # LBD_OBJ_Exporter rules: windows glass, structural types opaque, the
    # rest translucent unless an explicit alpha is present.
    assert row_opacity({"type": "https://w3id.org/product#Window"}) == 0.1
    assert row_opacity({"type": "https://w3id.org/product#Wall"}) == 1.0
    assert row_opacity({"type": "https://w3id.org/bot#Element"}) == 0.2
    assert row_opacity({"type": "https://w3id.org/product#Wall", "alpha": "0.4"}) == 0.4


def test_merge_obj_documents_offsets_faces() -> None:
    first = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
    second = "v 5 0 0\nv 6 0 0\nv 5 1 0\nf 1 2 3\n"
    merged = merge_obj_documents([first, second])
    lines = merged.splitlines()
    assert "o lbd_element_1" in lines and "o lbd_element_2" in lines
    faces = [line for line in lines if line.startswith("f ")]
    assert faces == ["f 1 2 3", "f 4 5 6"]


def test_export_merged_obj(tmp_path: Path) -> None:
    fragment = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
    target = tmp_path / "merged.obj"
    export_merged_obj([fragment, fragment], target)
    text = target.read_text(encoding="utf-8")
    assert text.count("v ") == 6
    assert text.count("f 1 2 3") == 1  # second fragment shifted: f 4 5 6
