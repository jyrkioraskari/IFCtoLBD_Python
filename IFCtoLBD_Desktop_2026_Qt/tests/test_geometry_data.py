import base64

from rdflib import Graph, Literal, Namespace, RDF, URIRef

from desktop.geometry_data import meshes_from_graph, parse_obj

OMG = Namespace("https://w3id.org/omg#")
FOG = Namespace("https://w3id.org/fog#")
INST = Namespace("https://example.org/model#")

OBJ = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"


def test_parse_obj() -> None:
    text = "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n"
    vertices, faces = parse_obj(text)
    assert vertices == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    assert faces == [(0, 1, 2), (0, 2, 3)]  # quad triangulated

    _, negative_faces = parse_obj("v 0 0 0\nv 1 0 0\nv 0 1 0\nf -3 -2 -1\n")
    assert negative_faces == [(0, 1, 2)]


def test_meshes_from_graph() -> None:
    graph = Graph()
    geometry = INST["wall_1_geometry"]
    graph.add((INST["wall_1"], OMG.hasGeometry, geometry))
    graph.add((geometry, RDF.type, URIRef("https://w3id.org/geo#Geometry")))
    graph.add((geometry, FOG["asObj_v3.0-obj"],
               Literal(base64.b64encode(OBJ.encode()).decode())))
    meshes = meshes_from_graph(graph)
    assert len(meshes) == 1
    assert meshes[0].name == "wall_1"
    assert len(meshes[0].vertices) == 3
    assert len(meshes[0].faces) == 1

    # Elements without an OBJ payload are skipped.
    graph.add((INST["wall_2"], OMG.hasGeometry, INST["wall_2_geometry"]))
    assert len(meshes_from_graph(graph)) == 1
