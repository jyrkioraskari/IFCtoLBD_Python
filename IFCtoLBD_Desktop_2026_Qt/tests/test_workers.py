from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, RDF, URIRef

from desktop.settings_model import ConversionSettings
from desktop.workers import apply_element_filters, resolve_input, run_conversion, run_read_in

SAMPLE = Path(__file__).resolve().parents[2] / "examples" / "data" / "two_walls.ifc"
BOT = Namespace("https://w3id.org/bot#")
PRODUCT = Namespace("https://w3id.org/product#")


def test_resolve_input_plain_ifc() -> None:
    source, cleanup = resolve_input(SAMPLE)
    assert source == SAMPLE
    assert cleanup is None


def test_resolve_input_missing() -> None:
    with pytest.raises(FileNotFoundError):
        resolve_input("does_not_exist.ifc")


def test_run_read_in() -> None:
    messages: list[str] = []
    summary, filters = run_read_in(ConversionSettings(ifc_file=str(SAMPLE)), messages.append)
    assert messages and "Reading IFC model" in messages[0]
    assert summary.schema == "IFC2X3"
    assert filters.element_type_counts


def test_run_conversion(tmp_path: Path) -> None:
    target = tmp_path / "two_walls_LBD.ttl"
    settings = ConversionSettings(ifc_file=str(SAMPLE), rdf_target=str(target))
    messages: list[str] = []
    output = run_conversion(settings, messages.append)
    assert output == str(target)
    assert target.is_file()
    graph = Graph()
    graph.parse(target)
    assert len(graph) >= 30
    assert len(set(graph.subjects(RDF.type, BOT.Building))) == 1


def test_run_conversion_jsonld(tmp_path: Path) -> None:
    target = tmp_path / "two_walls_LBD.jsonld"
    settings = ConversionSettings(ifc_file=str(SAMPLE), rdf_target=str(target),
                                 output_format="JSON-LD")
    output = run_conversion(settings, lambda _message: None)
    assert output.endswith(".jsonld")
    graph = Graph()
    graph.parse(target)
    assert (None, RDF.type, BOT.Building) in graph


def test_apply_element_filters() -> None:
    graph = Graph()
    wall = URIRef("https://example.org#wall_1")
    door = URIRef("https://example.org#door_1")
    for subject, product in ((wall, "Wall"), (door, "Door")):
        graph.add((subject, RDF.type, BOT.Element))
        graph.add((subject, RDF.type, PRODUCT[product]))
    graph.add((URIRef("https://example.org#storey_1"), BOT.containsElement, door))

    removed = apply_element_filters(graph, {"IfcWall"}, set())
    assert removed == 1
    assert (wall, None, None) in graph
    assert (door, None, None) not in graph
    assert (None, None, door) not in graph

    # An empty selection means the user unchecked every type.
    assert apply_element_filters(graph, set(), None) == 1
    assert (wall, None, None) not in graph


def test_conversion_filters_types_and_property_sets(tmp_path: Path) -> None:
    target = tmp_path / "filtered.ttl"
    settings = ConversionSettings(ifc_file=str(SAMPLE), rdf_target=str(target))
    run_conversion(
        settings,
        lambda _message: None,
        selected_types=set(),
        selected_psets={"Pset_BuildingCommon"},
    )
    graph = Graph().parse(target)
    assert not set(graph.subjects(RDF.type, BOT.Element))
    assert any("numberOfStoreys" in str(predicate) for predicate in graph.predicates())
    assert not any("loadBearing" in str(predicate) for predicate in graph.predicates())
