from __future__ import annotations

import base64
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping
from urllib.parse import quote

from rdflib import BNode, Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

from .config import ConversionProperties
from .namespaces import BOT, FOG, GEO, IFCOWL_BASE, OMG, OPM, PROPS


SUPPORTED_SCHEMAS = {
    "IFC2X3", "IFC2X3_FINAL", "IFC2X3_TC1", "IFC4", "IFC4_ADD1",
    "IFC4_ADD2", "IFC4_ADD2_TC1", "IFC4X1", "IFC4X3_RC1", "IFC4X3_ADD2",
}


class UnsupportedSchemaError(ValueError):
    pass


def _safe(value: Any) -> str:
    return quote(str(value).strip().replace(" ", "_"), safe="-._~")


def _value(value: Any) -> Any:
    return getattr(value, "wrappedValue", value)


class IFCtoLBDConverter:
    """Convert an IFC-SPF/IFCZIP model to an :class:`rdflib.Graph`.

    The constructor and camelCase methods intentionally mirror the Java API.
    """

    def __init__(self, base_uri: str = "https://dot.dc.rwth-aachen.de/IFCtoLBDset#", level: int = 1):
        self.base_uri = base_uri if base_uri.endswith(("#", "/")) else base_uri + "#"
        self.level = int(level)
        if self.level not in (1, 2, 3):
            raise ValueError("Property level must be 1, 2, or 3")
        self.property_replace_map: dict[str, str] = {}
        self.model = Graph()

    def setProperty_replace_map(self, replacements: Mapping[str, str] | str) -> None:
        if isinstance(replacements, str):
            data = json.loads(Path(replacements).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Replacement JSON must be an object")
            replacements = data
        self.property_replace_map = {str(k): str(v) for k, v in replacements.items()}

    set_property_replace_map = setProperty_replace_map

    def convert(self, ifc_file: str | Path, properties: ConversionProperties | None = None) -> Graph:
        props = properties or ConversionProperties()
        source, cleanup = self._resolve_input(Path(ifc_file))
        try:
            model = self._open_ifc(source)
            self.model = self._new_graph(model)
            resources = self._add_spatial_structure(model, props)
            if props.has_building_elements:
                self._add_elements(model, resources, props)
            if props.has_building_properties:
                self._add_properties(model, resources)
            if props.has_geolocation:
                self._add_geolocation(model, resources)
            if props.has_geometry:
                self._add_geometry(model, resources, props)
            if props.has_units:
                self._add_units(model)
            if props.export_ifcowl:
                self._add_ifcowl_links(model, resources)
            return self.model
        finally:
            if cleanup is not None:
                cleanup.unlink(missing_ok=True)

    def convert_to_file(
        self, ifc_file: str | Path, target_file: str | Path,
        properties: ConversionProperties | None = None, format: str | None = None,
    ) -> Graph:
        graph = self.convert(ifc_file, properties)
        graph.serialize(destination=str(target_file), format=format or self._format(target_file))
        return graph

    def getObjJSON(self, _query: str | None = None) -> str:
        rows = []
        for element, _, geometry in self.model.triples((None, OMG.hasGeometry, None)):
            obj = self.model.value(geometry, FOG["asObj_v3.0-obj"])
            if obj is not None:
                rows.append({"element": str(element), "obj": str(obj)})
        return json.dumps(rows)

    def close(self) -> None:
        self.model.close()

    def __enter__(self) -> "IFCtoLBDConverter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _open_ifc(path: Path) -> Any:
        try:
            import ifcopenshell
        except ImportError as exc:
            raise RuntimeError("Native conversion requires ifcopenshell (pip install ifctolbd)") from exc
        model = ifcopenshell.open(str(path))
        schema = str(model.schema).upper().replace(".", "_")
        if schema not in SUPPORTED_SCHEMAS and not schema.startswith(("IFC2X3", "IFC4")):
            raise UnsupportedSchemaError(f"Unsupported IFC schema: {schema}")
        return model

    @staticmethod
    def _resolve_input(path: Path) -> tuple[Path, Path | None]:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.suffix.lower() not in {".ifczip", ".zip"}:
            return path, None
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".ifc") and not n.endswith("/")]
            if len(names) != 1:
                raise ValueError("IFCZIP must contain exactly one .ifc file")
            handle = tempfile.NamedTemporaryFile(suffix=".ifc", delete=False)
            with handle, archive.open(names[0]) as source:
                handle.write(source.read())
            temp = Path(handle.name)
        return temp, temp

    def _new_graph(self, model: Any) -> Graph:
        graph = Graph()
        for prefix, ns in {"bot": BOT, "props": PROPS, "opm": OPM, "omg": OMG,
                           "fog": FOG, "geo": GEO, "inst": Namespace(self.base_uri)}.items():
            graph.bind(prefix, ns)
        return graph

    def _uri(self, entity: Any) -> URIRef:
        kind = entity.is_a()[3:].lower() if entity.is_a().lower().startswith("ifc") else entity.is_a().lower()
        identity = getattr(entity, "GlobalId", None) or entity.id()
        return URIRef(f"{self.base_uri}{kind}_{_safe(identity)}")

    @staticmethod
    def _entities(model: Any, name: str) -> Iterable[Any]:
        try:
            return model.by_type(name)
        except RuntimeError:
            return ()

    def _add_spatial_structure(self, model: Any, props: ConversionProperties) -> dict[int, URIRef]:
        result: dict[int, URIRef] = {}
        types = {"IfcSite": BOT.Site, "IfcBuilding": BOT.Building,
                 "IfcBuildingStorey": BOT.Storey, "IfcSpace": BOT.Space}
        for ifc_type, rdf_type in types.items():
            for entity in self._entities(model, ifc_type):
                uri = result[entity.id()] = self._uri(entity)
                self.model.add((uri, RDF.type, rdf_type))
                self._add_identity(entity, uri)
        relation_predicates = {
            "IfcSite": BOT.hasBuilding, "IfcBuilding": BOT.hasStorey,
            "IfcBuildingStorey": BOT.hasSpace, "IfcSpace": BOT.containsElement,
        }
        for rel in self._entities(model, "IfcRelAggregates"):
            parent = getattr(rel, "RelatingObject", None)
            if parent is None or parent.id() not in result:
                continue
            predicate = relation_predicates.get(parent.is_a(), BOT.containsZone)
            for child in getattr(rel, "RelatedObjects", ()):
                if child.id() in result:
                    self.model.add((result[parent.id()], predicate, result[child.id()]))
        return result

    def _add_elements(self, model: Any, resources: dict[int, URIRef], props: ConversionProperties) -> None:
        excluded = {"IfcSpatialElement", "IfcSpatialStructureElement", "IfcProject"}
        for entity in self._entities(model, "IfcElement"):
            if entity.is_a() in excluded:
                continue
            uri = resources[entity.id()] = self._uri(entity)
            self.model.add((uri, RDF.type, BOT.Element))
            product_type = URIRef(f"https://w3id.org/product#{_safe(entity.is_a()[3:])}")
            self.model.add((uri, RDF.type, product_type))
            self._add_identity(entity, uri)
            for rel in getattr(entity, "ContainedInStructure", ()):
                parent = getattr(rel, "RelatingStructure", None)
                if parent is not None and parent.id() in resources:
                    self.model.add((resources[parent.id()], BOT.containsElement, uri))

    def _add_identity(self, entity: Any, uri: URIRef) -> None:
        if getattr(entity, "Name", None):
            self.model.add((uri, RDFS.label, Literal(entity.Name)))
        if getattr(entity, "GlobalId", None):
            self.model.add((uri, PROPS.globalIdIfcRoot, Literal(entity.GlobalId)))

    def _add_properties(self, model: Any, resources: dict[int, URIRef]) -> None:
        for rel in self._entities(model, "IfcRelDefinesByProperties"):
            definition = getattr(rel, "RelatingPropertyDefinition", None)
            if definition is None:
                continue
            values = list(self._property_values(definition))
            for entity in getattr(rel, "RelatedObjects", ()):
                subject = resources.get(entity.id())
                if subject is None:
                    continue
                for name, value, unit in values:
                    self._emit_property(subject, definition, name, value, unit)

    def _property_values(self, definition: Any) -> Iterator[tuple[str, Any, Any]]:
        properties = getattr(definition, "HasProperties", None) or getattr(definition, "Quantities", ())
        for prop in properties:
            name = str(getattr(prop, "Name", prop.is_a()))
            if prop.is_a("IfcComplexProperty"):
                yield from self._property_values(prop)
                continue
            value = None
            for attr in ("NominalValue", "LengthValue", "AreaValue", "VolumeValue", "CountValue",
                         "WeightValue", "TimeValue", "EnumerationValues", "ListValues"):
                candidate = getattr(prop, attr, None)
                if candidate is not None:
                    value = candidate
                    break
            if isinstance(value, (tuple, list)):
                value = ", ".join(str(_value(v)) for v in value)
            if value is not None:
                yield name, _value(value), getattr(prop, "Unit", None)

    def _emit_property(self, subject: URIRef, pset: Any, name: str, value: Any, unit: Any) -> None:
        mapped = self.property_replace_map.get(name, name)
        predicate = URIRef(f"{PROPS}{_safe(mapped[0].lower() + mapped[1:] if mapped else 'property')}")
        literal = self._literal(value)
        if self.level == 1:
            self.model.add((subject, predicate, literal))
            return
        node = BNode() if self.level == 2 else URIRef(
            f"{self.base_uri}property_{_safe(getattr(pset, 'Name', 'set'))}_{_safe(mapped)}_{pset.id()}"
        )
        self.model.add((subject, predicate, node))
        self.model.add((node, RDF.type, OPM.Property))
        self.model.add((node, OPM.hasPropertyState, literal))
        if unit is not None:
            self.model.add((node, PROPS.unit, Literal(str(unit))))

    @staticmethod
    def _literal(value: Any) -> Literal:
        if isinstance(value, bool):
            return Literal(value, datatype=XSD.boolean)
        if isinstance(value, int):
            return Literal(value, datatype=XSD.integer)
        if isinstance(value, float):
            return Literal(value, datatype=XSD.double)
        return Literal(value)

    def _add_geolocation(self, model: Any, resources: dict[int, URIRef]) -> None:
        for site in self._entities(model, "IfcSite"):
            uri = resources.get(site.id())
            lat, lon = getattr(site, "RefLatitude", None), getattr(site, "RefLongitude", None)
            if uri and lat and lon:
                latitude, longitude = self._dms(lat), self._dms(lon)
                self.model.add((uri, GEO.asWKT, Literal(f"POINT({longitude} {latitude})", datatype=GEO.wktLiteral)))

    @staticmethod
    def _dms(parts: Iterable[int]) -> float:
        values = list(parts)
        sign = -1 if values[0] < 0 else 1
        result = abs(values[0]) + values[1] / 60 + values[2] / 3600
        if len(values) > 3:
            result += values[3] / 3_600_000_000
        return sign * result

    def _add_geometry(self, model: Any, resources: dict[int, URIRef], props: ConversionProperties) -> None:
        try:
            import ifcopenshell.geom
        except ImportError as exc:
            raise RuntimeError("Geometry conversion requires ifcopenshell.geom") from exc
        settings = ifcopenshell.geom.settings()
        for entity_id, uri in list(resources.items()):
            entity = model.by_id(entity_id)
            if not getattr(entity, "Representation", None):
                continue
            try:
                shape = ifcopenshell.geom.create_shape(settings, entity)
            except Exception:
                continue
            verts, faces = shape.geometry.verts, shape.geometry.faces
            lines = [f"v {verts[i]} {verts[i+1]} {verts[i+2]}" for i in range(0, len(verts), 3)]
            lines += [f"f {faces[i]+1} {faces[i+1]+1} {faces[i+2]+1}" for i in range(0, len(faces), 3)]
            encoded = base64.b64encode(("\n".join(lines) + "\n").encode()).decode()
            geometry = URIRef(f"{uri}_geometry")
            self.model.add((uri, OMG.hasGeometry, geometry))
            self.model.add((geometry, RDF.type, GEO.Geometry))
            self.model.add((geometry, FOG["asObj_v3.0-obj"], Literal(encoded)))
            if props.has_bounding_box_wkt and verts:
                xyz = list(zip(verts[0::3], verts[1::3], verts[2::3]))
                lo = tuple(min(p[n] for p in xyz) for n in range(3))
                hi = tuple(max(p[n] for p in xyz) for n in range(3))
                self.model.add((geometry, GEO.asWKT, Literal(self._box_wkt(lo, hi), datatype=GEO.wktLiteral)))

    @staticmethod
    def _box_wkt(lo: tuple[float, ...], hi: tuple[float, ...]) -> str:
        x0, y0, z0 = lo; x1, y1, z1 = hi
        return ("POLYHEDRALSURFACE Z ("
                f"(({x0} {y0} {z0},{x1} {y0} {z0},{x1} {y1} {z0},{x0} {y1} {z0},{x0} {y0} {z0})),"
                f"(({x0} {y0} {z1},{x0} {y1} {z1},{x1} {y1} {z1},{x1} {y0} {z1},{x0} {y0} {z1})))")

    def _add_units(self, model: Any) -> None:
        for project in self._entities(model, "IfcProject"):
            assignment = getattr(project, "UnitsInContext", None)
            for unit in getattr(assignment, "Units", ()):
                node = URIRef(f"{self.base_uri}unit_{unit.id()}")
                self.model.add((node, RDF.type, PROPS.Unit))
                self.model.add((node, RDFS.label, Literal(str(unit))))

    def _add_ifcowl_links(self, model: Any, resources: dict[int, URIRef]) -> None:
        ifc = Namespace(IFCOWL_BASE)
        for entity_id, uri in resources.items():
            entity = model.by_id(entity_id)
            self.model.add((uri, RDF.type, ifc[entity.is_a()]))

    @staticmethod
    def _format(path: str | Path) -> str:
        return {".ttl": "turtle", ".nt": "nt", ".jsonld": "json-ld", ".rdf": "xml",
                ".xml": "xml", ".trig": "trig"}.get(Path(path).suffix.lower(), "turtle")

