"""Geometry colouring, opacity and merged-OBJ export.

Ported from Jyrki Oraskari's LBD_OBJ_Exporter
(https://github.com/jyrkioraskari/LBD_OBJ_Exporter, Apache-2.0) and adapted
for the desktop replica: the SPARQL geometry query, the MTL ``Kd`` colour and
alpha parsing, the per-type opacity rules (windows render as glass, walls,
beams, slabs, doors and roofs stay opaque, anything else is translucent), and
the merged Wavefront OBJ writer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

DEFAULT_WINDOW_ALPHA = 0.1
DEFAULT_TRANSPARENT_ALPHA = 0.2
DEFAULT_MATERIAL_COLOR = (184, 190, 188)

# Display palette used when the RDF output carries no MTL Kd colour. The
# LBD_OBJ_Exporter falls back to a single default material; the replica adds
# per-type display colours so type-rich models are readable at a glance.
TYPE_DISPLAY_COLORS: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("Wall", (211, 205, 196)),
    ("Slab", (200, 204, 208)),
    ("Roof", (180, 95, 95)),
    ("Door", (160, 82, 45)),
    ("Window", (158, 201, 232)),
    ("Beam", (201, 179, 126)),
    ("Member", (201, 179, 126)),
    ("Column", (201, 179, 126)),
    ("Stair", (184, 192, 204)),
    ("StairFlight", (184, 192, 204)),
    ("Railing", (184, 192, 204)),
    ("Furniture", (212, 184, 150)),
    ("Furnishing", (212, 184, 150)),
    ("Covering", (206, 206, 196)),
    ("Footing", (170, 166, 160)),
    ("Space", (150, 170, 200)),
    ("Site", (170, 200, 150)),
)

OPAQUE_TYPE_PREFIXES = ("Wall", "Beam", "Member", "Column", "Slab", "Door", "Roof",
                        "Stair", "Railing", "Furniture", "Furnishing", "Footing")


def geometry_query() -> str:
    """The LBD_OBJ_Exporter geometry query: OBJ payloads with Kd/alpha data."""
    return """PREFIX bot: <https://w3id.org/bot#>
PREFIX fog: <https://w3id.org/fog#>
PREFIX lbd: <https://lbd.org/#>
PREFIX omg: <https://w3id.org/omg#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?element ?type ?isWindow ?kd ?alpha ?obj WHERE {
  ?element omg:hasGeometry ?geometry .
  ?geometry fog:asObj_v3.0-obj ?obj .
  OPTIONAL { ?geometry lbd:asMTL_kd ?geometryKd }
  OPTIONAL { ?element lbd:asMTL_kd ?elementKd }
  BIND(COALESCE(?geometryKd, ?elementKd) AS ?kd)
  OPTIONAL { ?geometry lbd:asMTL_alpha ?geometryAlpha }
  OPTIONAL { ?element lbd:asMTL_alpha ?elementAlpha }
  OPTIONAL { ?element rdf:type ?type }
  BIND(REGEX(STR(?type), "buildingelement#Window($|-)") AS ?isWindow)
  BIND(COALESCE(?geometryAlpha, ?elementAlpha) AS ?alpha)
}
"""


def local_type_name(type_value: str) -> str:
    return type_value.rsplit("#", 1)[-1].rsplit("/", 1)[-1].rsplit(":", 1)[-1]


def is_window_type(local_name: str) -> bool:
    return local_name == "Window" or local_name.startswith("Window")


def is_opaque_type(local_name: str) -> bool:
    return any(local_name.startswith(prefix) for prefix in OPAQUE_TYPE_PREFIXES)


def display_color(local_name: str) -> tuple[int, int, int]:
    for prefix, color in TYPE_DISPLAY_COLORS:
        if local_name.startswith(prefix):
            return color
    return DEFAULT_MATERIAL_COLOR


def type_specificity(local_name: str) -> int:
    """1 when the type is known (colour/opacity rules apply), else 0."""
    if is_window_type(local_name) or is_opaque_type(local_name):
        return 1
    return 0 if display_color(local_name) == DEFAULT_MATERIAL_COLOR else 1


def row_opacity(row: Mapping[str, str]) -> float:
    """Opacity rules from LBD_OBJ_Exporter, adapted for prefix matching."""
    type_name = local_type_name(row.get("type", ""))
    alpha = row.get("alpha", "")
    if alpha:
        return parse_alpha(alpha)
    if is_window_type(type_name):
        return DEFAULT_WINDOW_ALPHA
    if is_opaque_type(type_name):
        return 1.0
    return DEFAULT_TRANSPARENT_ALPHA


def parse_kd_color(value: str) -> tuple[int, int, int] | None:
    """Parse an MTL Kd value: '#rrggbb' or three floats (0-1 or 0-255)."""
    value = value.strip()
    if not value:
        return None
    if value.startswith("#") and len(value) == 7:
        try:
            return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
        except ValueError:
            return None
    parts = value.replace(",", " ").split()
    if len(parts) >= 3:
        try:
            numbers = [float(part) for part in parts[:3]]
        except ValueError:
            return None
        if all(0.0 <= number <= 1.0 for number in numbers):
            return tuple(int(round(number * 255)) for number in numbers)  # type: ignore[return-value]
        if all(0.0 <= number <= 255.0 for number in numbers):
            return tuple(max(0, min(255, int(round(number)))) for number in numbers)  # type: ignore[return-value]
    return None


def parse_alpha(value: str) -> float:
    value = value.strip()
    if not value:
        return 1.0
    try:
        alpha = float(value)
    except ValueError:
        return 1.0
    return max(0.0, min(1.0, alpha))


def adjust_face_token(token: str, vertex_offset: int, texture_offset: int, normal_offset: int) -> str:
    parts = token.split("/")
    offsets = (vertex_offset, texture_offset, normal_offset)
    adjusted: list[str] = []
    for index, part in enumerate(parts):
        if not part:
            adjusted.append(part)
            continue
        value = int(part)
        if value > 0:
            value += offsets[index]
        adjusted.append(str(value))
    return "/".join(adjusted)


def merge_obj_documents(obj_documents: Iterable[str]) -> str:
    """Merge OBJ fragments into one document (LBD_OBJ_Exporter writer)."""
    merged_lines: list[str] = ["# Exported from IFCtoLBD Desktop (Qt)"]
    vertex_offset = texture_offset = normal_offset = 0

    for index, obj_document in enumerate(obj_documents, start=1):
        local_vertices = local_textures = local_normals = 0
        merged_lines.append("")
        merged_lines.append(f"o lbd_element_{index}")
        for raw_line in obj_document.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("mtllib"):
                continue
            prefix, _, rest = line.partition(" ")
            if prefix == "v":
                local_vertices += 1
                merged_lines.append(line)
            elif prefix == "vt":
                local_textures += 1
                merged_lines.append(line)
            elif prefix == "vn":
                local_normals += 1
                merged_lines.append(line)
            elif prefix == "f":
                merged_lines.append("f " + " ".join(
                    adjust_face_token(token, vertex_offset, texture_offset, normal_offset)
                    for token in rest.split()))
            else:
                merged_lines.append(line)
        vertex_offset += local_vertices
        texture_offset += local_textures
        normal_offset += local_normals

    return "\n".join(merged_lines).rstrip() + "\n"


def export_merged_obj(obj_documents: Iterable[str], output_path: str | Path) -> str:
    merged = merge_obj_documents(obj_documents)
    Path(output_path).write_text(merged, encoding="utf-8")
    return merged
