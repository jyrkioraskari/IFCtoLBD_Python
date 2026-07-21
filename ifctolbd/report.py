"""Property report port of IFCProps2ExcelOnline."""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph, RDF

from .namespaces import BOT


def write_property_report(graph: Graph, target: str | Path) -> None:
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise RuntimeError("Excel export requires: pip install 'ifctolbd[excel]'") from exc
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "IFC properties"
    sheet.append(("element", "type", "property", "value"))
    element_types = {BOT.Element, BOT.Site, BOT.Building, BOT.Storey, BOT.Space}
    subjects = {s for s, _, kind in graph.triples((None, RDF.type, None)) if kind in element_types}
    for subject in sorted(subjects, key=str):
        types = ", ".join(sorted(str(o) for o in graph.objects(subject, RDF.type)))
        for predicate, value in sorted(graph.predicate_objects(subject), key=lambda row: str(row[0])):
            if predicate != RDF.type:
                sheet.append((str(subject), types, str(predicate), str(value)))
    workbook.save(target)

