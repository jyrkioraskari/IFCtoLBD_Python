from pathlib import Path

from rdflib import Graph, URIRef

from desktop.geometry_data import load_meshes_from_output
from desktop.settings_model import ConversionSettings
from desktop.workers import run_conversion

SAMPLE = Path(__file__).resolve().parents[2] / "examples" / "data" / "two_walls.ifc"


def test_geometry_conversion_produces_preview_meshes(tmp_path: Path) -> None:
    target = tmp_path / "two_walls_LBD.ttl"
    settings = ConversionSettings(
        ifc_file=str(SAMPLE),
        rdf_target=str(target),
        has_geometry=True,
        has_bounding_box_wkt=True,
    )
    messages: list[str] = []
    output = run_conversion(settings, messages.append)
    assert any("2 element meshes" in message for message in messages)
    meshes = load_meshes_from_output(output)
    assert len(meshes) == 2  # the two walls of the sample model
    for mesh in meshes:
        assert mesh.vertices
        assert mesh.faces
        assert mesh.obj_text  # raw OBJ kept for the merged export
        assert mesh.type_name == "WallStandardCase"
        assert mesh.opacity == 1.0  # walls are opaque in LBD_OBJ_Exporter rules
        assert mesh.color == (128, 128, 128)  # IfcOpenShell diffuse material

    # Product placements must be baked into each OBJ fragment so the merged
    # preview forms a building instead of stacking all products at the origin.
    y_ranges = [(min(vertex[1] for vertex in mesh.vertices),
                 max(vertex[1] for vertex in mesh.vertices)) for mesh in meshes]
    assert max(high for _, high in y_ranges) - min(low for low, _ in y_ranges) > 3.0

    graph = Graph().parse(output)
    assert any(graph.triples((None, URIRef("https://lbd.org/#asMTL_kd"), None)))


def test_geometry_request_without_shapes_warns(tmp_path: Path, monkeypatch) -> None:
    """A geometry request that produces no meshes must be reported in the log."""
    import desktop.workers as workers

    target = tmp_path / "no_shapes_LBD.ttl"
    settings = ConversionSettings(
        ifc_file=str(SAMPLE),
        rdf_target=str(target),
        has_geometry=True,
    )
    # Point the counter at a nonexistent property: zero meshes found even
    # though geometry was requested (as with an IfcOpenShell without geom).
    monkeypatch.setattr(workers, "HAS_GEOMETRY", "https://w3id.org/omg#geometry_MISSING")
    messages: list[str] = []
    workers.run_conversion(settings, messages.append)
    assert any("no geometry was generated" in message for message in messages)
