"""SHACL validation of the latest RDF output, shape by shape.

Replicates the Java desktop's Validate card: shapes loaded from TTL files are
listed individually, and each shape is validated separately so the list can
show per-shape conform status.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rdflib import Graph, RDF, URIRef

SH_NODE_SHAPE = URIRef("http://www.w3.org/ns/shacl#NodeShape")
SH_TARGET_CLASS = URIRef("http://www.w3.org/ns/shacl#targetClass")

DEFAULT_RULESET = Path(__file__).resolve().parent / "resources" / "SHACL_rulesetLevel1.ttl"


@dataclass(slots=True)
class ShapeValidationItem:
    source_name: str
    source_path: str
    display_name: str
    shape_node: URIRef
    target_class: str = ""
    conforms: bool | None = None
    message: str = "Ready to validate"

    def row_text(self) -> str:
        return f"{self.display_name}\n{self.source_name}"


def parse_shape_items(source_path: str | Path, source_name: str | None = None) -> list[ShapeValidationItem]:
    shapes_graph = Graph()
    shapes_graph.parse(str(source_path))
    name = source_name or Path(source_path).name
    items: list[ShapeValidationItem] = []
    for shape in sorted(set(shapes_graph.subjects(RDF.type, SH_NODE_SHAPE)), key=str):
        display = str(shape).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        target_class = shapes_graph.value(shape, SH_TARGET_CLASS)
        items.append(ShapeValidationItem(
            source_name=name,
            source_path=str(source_path),
            display_name=display,
            shape_node=shape,
            target_class="" if target_class is None else str(target_class),
        ))
    return items


def load_default_shapes() -> list[ShapeValidationItem]:
    return parse_shape_items(DEFAULT_RULESET)


def _copy_subtree(source_graph: Graph, single: Graph, node) -> None:
    """Copy a node's triples, recursing into blank-node constraint objects."""
    from rdflib import BNode

    for predicate, obj in source_graph.predicate_objects(node):
        single.add((node, predicate, obj))
        if isinstance(obj, BNode):
            _copy_subtree(source_graph, single, obj)


def _single_shape_graph(item: ShapeValidationItem) -> Graph:
    """Extract only this item's shape (with its constraints) into a graph."""
    source_graph = Graph()
    source_graph.parse(item.source_path)
    single = Graph()
    for prefix, namespace in source_graph.namespaces():
        single.bind(prefix, namespace)
    single.add((item.shape_node, RDF.type, SH_NODE_SHAPE))
    _copy_subtree(source_graph, single, item.shape_node)
    return single


def validate_item(item: ShapeValidationItem, output_file: str) -> tuple[bool | None, str]:
    """Validate the item's shape against the RDF output using pyshacl."""
    try:
        import pyshacl
    except ImportError:
        return None, "pyshacl is not installed (run: pip install pyshacl)"

    try:
        data_graph = Graph()
        data_graph.parse(output_file)
        conforms, _results_graph, results_text = pyshacl.validate(
            data_graph=data_graph, shacl_graph=_single_shape_graph(item), inference="none",
        )
    except Exception as error:  # pyshacl raises assorted errors on bad shapes
        return None, f"Validation failed: {error}"
    if conforms:
        return True, "The RDF output conforms to this shape."
    return False, ("The RDF output does not conform to this shape.\n" + (results_text or "")).strip()
