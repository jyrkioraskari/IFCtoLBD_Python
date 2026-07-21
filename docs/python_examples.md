# Python examples

The repository includes a native Python example—no JVM, Java archives, or
JPype bridge is required.

Install the dependencies in a virtual environment and run the bundled two-wall
example directly from the checkout:

```bash
python -m pip install rdflib ifcopenshell
python examples/basic_conversion.py
```

This writes `two_walls.ttl` and prints the number of generated RDF triples.
Pass another IFC file and output path when needed:

```bash
python examples/basic_conversion.py model.ifc --output model.ttl
```

The equivalent library usage is:

```python
from ifctolbd import IFCtoLBDConverter

with IFCtoLBDConverter("https://example.org/building#", level=3) as converter:
    graph = converter.convert_to_file("model.ifc", "model.ttl")

print(f"Generated {len(graph)} triples")
```
