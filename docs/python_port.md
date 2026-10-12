# Native Python port

The `ifctolbd` package replaces the Java modules and the former JPype bridge.
It uses IfcOpenShell for IFC ingestion and geometry, RDFLib for RDF, FastAPI for
the HTTP surface, PySide6 for the desktop surface, and openpyxl for reports.

## Install and convert

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[api,desktop,excel,test]'
ifctolbd model.ifc model.ttl --level 3 --geolocation
```

The library interface follows the Java names where that aids migration:

```python
from ifctolbd import ConversionProperties, IFCtoLBDConverter

options = ConversionProperties()
options.setHasGeometry(True)
graph = IFCtoLBDConverter("https://example.org/model/", 3).convert("model.ifc", options)
graph.serialize("model.ttl")
```

Run the REST replacement with:

```bash
pip install -e '.[api]'
uvicorn ifctolbd.api:app
```

Run the desktop replacement with `python -m ifctolbd.desktop`. Reports can be
created with `ifctolbd.report.write_property_report(graph, "report.xlsx")`.

## Module mapping

| Java project | Python replacement |
|---|---|
| `IFCtoRDF` | IfcOpenShell ingestion plus `rdflib.Graph` |
| `IFCtoLBD` | `ifctolbd.converter`, `config`, `namespaces`, `guid`, `cli` |
| `IFCtoLBD_Geometry` | `ifctolbd.converter._add_geometry` |
| `IFCtoLBD_OpenAPI` | `ifctolbd.api` |
| `IFCtoLBD_Desktop*` | `ifctolbd.desktop` |
| `IFCProps2ExcelOnline` | `ifctolbd.report` |

The native API returns RDFLib graphs rather than emulating Apache Jena objects.
Callers should use RDFLib's `triples`, `subjects`, `query`, and `serialize`
methods. The old `IFCtoLBD_wrapper` import remains available for converter and
configuration compatibility, but JVM lifecycle functions are deprecated no-ops.

