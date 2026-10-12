from pathlib import Path

from desktop.sparql_runner import DEFAULT_SPARQL_QUERY, run_sparql_query
from desktop.shacl_validator import DEFAULT_RULESET, load_default_shapes, parse_shape_items

SAMPLE = Path(__file__).resolve().parents[2] / "examples" / "data" / "two_walls.ifc"
TWO_WALLS_TTL = """\
@prefix bot: <https://w3id.org/bot#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<https://example.org#building> a bot:Building ; rdfs:label "Test building" .
<https://example.org#element> a bot:Element ; rdfs:label "Test element" .
"""


def test_default_ruleset_bundled() -> None:
    assert DEFAULT_RULESET.is_file()
    items = load_default_shapes()
    assert items, "the default SHACL ruleset must provide at least one shape"
    assert all(item.conforms is None for item in items)
    assert all(item.source_name == "SHACL_rulesetLevel1.ttl" for item in items)


def test_parse_shape_items_counts_shapes(tmp_path: Path) -> None:
    path = tmp_path / "shapes.ttl"
    path.write_text(TWO_WALLS_TTL, encoding="utf-8")
    items = parse_shape_items(path, "custom name")
    assert items == []  # no sh:NodeShape declarations in this document


def test_sparql_query_against_output(tmp_path: Path) -> None:
    output = tmp_path / "model.ttl"
    output.write_text(TWO_WALLS_TTL, encoding="utf-8")
    result = run_sparql_query(str(output), DEFAULT_SPARQL_QUERY)
    assert result.columns == ("element",)
    assert result.rows == (("https://example.org#element",),)
    assert result.message == "1 row(s)"


def test_sparql_ask_query(tmp_path: Path) -> None:
    output = tmp_path / "model.ttl"
    output.write_text(TWO_WALLS_TTL, encoding="utf-8")
    result = run_sparql_query(str(output), "ASK { ?s a <https://w3id.org/bot#Building> }")
    assert result.columns == ("Result",)
    assert result.rows == (("true",),)
    assert "ASK" in result.message
