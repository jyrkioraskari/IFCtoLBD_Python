# IFCtoLBD Python

IFCtoLBD converts Industry Foundation Classes (IFC) models into RDF graphs
that use the Linked Building Data ontologies. This is a native Python
implementation built with [IfcOpenShell](https://ifcopenshell.org/) and
[RDFLib](https://rdflib.readthedocs.io/); Java, a JVM, and JPype are not
required.

The converter supports IFC STEP files (`.ifc`) and IFCZIP archives (`.ifczip`
or `.zip`). It can write Turtle, JSON-LD, RDF/XML, and other formats supported
by RDFLib.

## Requirements

* Python 3.10 or newer
* IfcOpenShell 0.8 or newer
* RDFLib 7 or newer

## Installation

Create a virtual environment and install the project:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On Windows, activate the environment with:

```powershell
.venv\\Scripts\\Activate.ps1
```

Optional dependency groups are available for the REST API, desktop UI, Excel
reports, and tests:

```bash
python -m pip install -e '.\[api,desktop,excel,test]'
```

## Quick start

The repository includes a small two-wall IFC model. Run the example from the
repository root:

```bash
python examples/basic\_conversion.py
```

It creates `two\_walls.ttl` and reports the number of RDF triples. To convert
another model:

```bash
python examples/basic\_conversion.py path/to/model.ifc --output model.ttl
```

## Command line

After installation, use the `ifctolbd` command:

```bash
ifctolbd model.ifc model.ttl --level 3
```

Common options include:

```text
--base-uri URI          Base URI for generated resources
--level {1,2,3}         Property output level
--geometry              Include geometry
--geolocation           Include geolocation
--units                 Include units
--bounding-box-wkt      Include bounding boxes as WKT
--no-properties         Omit building properties
--no-ifcowl             Omit links to IFC-OWL resources
```

Run `ifctolbd --help` for the complete command reference. The RDF format is
inferred from the output filename.

## Python API

```python
from ifctolbd import ConversionProperties, IFCtoLBDConverter

options = ConversionProperties(
    has\_geometry=False,
    has\_geolocation=True,
    has\_units=True,
)

with IFCtoLBDConverter("https://example.org/building#", level=3) as converter:
    graph = converter.convert("model.ifc", options)
    graph.serialize(destination="model.ttl", format="turtle")

print(f"Generated {len(graph)} triples")
```

`convert()` returns an `rdflib.Graph`, so standard RDFLib operations such as
`triples()`, `subjects()`, `query()`, and `serialize()` can be used directly.
For a one-step conversion, use `convert\_to\_file()`:

```python
with IFCtoLBDConverter() as converter:
    converter.convert\_to\_file("model.ifczip", "model.jsonld")
```

## Optional interfaces

### REST API

```bash
python -m pip install -e '.\[api]'
uvicorn ifctolbd.api:app
```

The service exposes `GET /hello` and `POST /convertIFCtoLBD`. Interactive API
documentation is available at `http://127.0.0.1:8000/docs` while it is running.

### Desktop application

```bash
python -m pip install -e '.\[desktop]'
python -m ifctolbd.desktop
```

### Excel property reports

```python
from ifctolbd.report import write\_property\_report

write\_property\_report(graph, "properties.xlsx")
```

Install this feature with `python -m pip install -e '.\[excel]'`.

## Testing

```bash
python -m pip install -e '.\[test]'
python -m pytest -q
```

## Documentation

* [Python examples](docs/python_examples.md)
* [Python implementation guide](docs/python_port.md)

## License

IFCtoLBD is licensed under the [Apache License 2.0](LICENSE).

