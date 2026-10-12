"""Geometry preview data: OBJ meshes from the RDF output, coloured per element.

Mesh extraction follows LBD_OBJ_Exporter
(https://github.com/jyrkioraskari/LBD_OBJ_Exporter): a SPARQL query pulls the
base64 OBJ payloads together with any MTL Kd colour / alpha annotations, and
the LBD_OBJ_Exporter opacity rules decide how each element renders (windows
are glass, structural types are opaque, the rest is translucent).
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass, field

from .obj_exporter import (
    DEFAULT_MATERIAL_COLOR, display_color, geometry_query, local_type_name,
    parse_kd_color, row_opacity, type_specificity,
)

HAS_GEOMETRY = "https://w3id.org/omg#hasGeometry"
AS_OBJ = "https://w3id.org/fog#asObj_v3.0-obj"

MAX_PREVIEW_FACES = 400_000


@dataclass(slots=True)
class Mesh:
    name: str
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    faces: list[tuple[int, int, int]] = field(default_factory=list)
    color: tuple[int, int, int] = DEFAULT_MATERIAL_COLOR
    opacity: float = 1.0
    type_name: str = ""
    obj_text: str = ""


def parse_obj(text: str) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """Parse the v/f subset of the Wavefront OBJ format the converter emits."""
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("v "):
            parts = line.split()
            if len(parts) >= 4:
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif line.startswith("f "):
            indices: list[int] = []
            for token in line.split()[1:]:
                value = int(token.split("/")[0])
                indices.append(len(vertices) + value if value < 0 else value - 1)
            for i in range(1, len(indices) - 1):
                faces.append((indices[0], indices[i], indices[i + 1]))
    return vertices, faces


def _decode_obj_literal(value: str) -> str:
    try:
        return base64.b64decode("".join(value.split()), validate=True).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return ""


def meshes_from_graph(graph, face_limit: int = MAX_PREVIEW_FACES) -> list[Mesh]:
    """Extract one coloured Mesh per element, following LBD_OBJ_Exporter.

    One element appears in one row per RDF type; the rows are merged, keeping
    the MTL colour/alpha bindings and the most specific type name.
    """
    results = graph.query(geometry_query())
    variables = [str(variable) for variable in (getattr(results, "vars", None) or [])]
    if not variables:
        return []

    groups: dict[tuple[str, str], dict[str, str]] = {}
    order: list[tuple[str, str]] = []
    for row in results:
        bindings = {str(key): str(value) for key, value in row.asdict().items()}
        element = bindings.get("element", "")
        encoded = bindings.get("obj", "")
        if not element or not encoded:
            continue
        key = (element, encoded)
        if key not in groups:
            groups[key] = {"element": element, "obj": encoded}
            order.append(key)
        group = groups[key]
        for field_name in ("kd", "alpha"):
            if bindings.get(field_name, ""):
                group.setdefault(field_name, bindings[field_name])
        new_type = bindings.get("type", "")
        if new_type:
            existing_type = group.get("type", "")
            if (not existing_type
                    or type_specificity(local_type_name(new_type)) > type_specificity(local_type_name(existing_type))):
                group["type"] = new_type

    meshes: list[Mesh] = []
    remaining = face_limit
    for key in order:
        group = groups[key]
        obj_text = _decode_obj_literal(group["obj"])
        if not obj_text:
            continue
        vertices, faces = parse_obj(obj_text)
        if not vertices or not faces:
            continue
        if len(faces) > remaining:
            faces = faces[:remaining]
        type_name = local_type_name(group.get("type", ""))
        color = parse_kd_color(group.get("kd", "")) or display_color(type_name)
        meshes.append(Mesh(
            name=group["element"].rsplit("#", 1)[-1].rsplit("/", 1)[-1],
            vertices=vertices,
            faces=faces,
            color=color,
            opacity=row_opacity(group),
            type_name=type_name,
            obj_text=obj_text,
        ))
        remaining -= len(faces)
        if remaining <= 0:
            break
    return meshes


def load_meshes_from_output(output_file: str, face_limit: int = MAX_PREVIEW_FACES) -> list[Mesh]:
    from rdflib import Graph

    graph = Graph()
    graph.parse(output_file)
    return meshes_from_graph(graph, face_limit)


def _rotate(point: tuple[float, float, float], rx: float, ry: float) -> tuple[float, float, float]:
    x, y, z = point
    # Rotate around Y.
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    # Rotate around X.
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    return x, y, z
