# IFCtoLBD_Desktop_2026_Qt

A Qt (PySide6) replica of the JavaFX
[IFCtoLBD_Desktop_2026](https://github.com/jyrkioraskari/IFCtoLBD/tree/master/IFCtoLBD_Desktop_2026)
desktop application, driven by the **native Python converter** in this
repository (`ifctolbd`, built on IfcOpenShell and RDFLib). No JVM, JPype, or
Java libraries are involved.

## Layout

```
IFCtoLBD_Desktop_2026_Qt/
├── main.py                  # application entry point
├── desktop/
│   ├── main_window.py       # window shell, workflow, floating cards
│   ├── settings_model.py    # ConversionSettings record + preference keys
│   ├── workers.py           # read-in and conversion background threads
│   ├── model_summary.py     # model statistics and filter inventories
│   ├── geometry_data.py     # OBJ mesh extraction from the RDF output
│   ├── geometry_preview.py  # interactive PyVista/VTK preview + fallback
│   ├── obj_exporter.py      # LBD_OBJ_Exporter port: colours, glass, OBJ merge
│   ├── sparql_runner.py     # SPARQL execution against the RDF output
│   ├── shacl_validator.py   # per-shape SHACL validation (pyshacl)
│   ├── command_line.py      # "Copy command line" equivalent
│   └── resources/
│       ├── app.qss          # replica of the JavaFX stylesheet
│       └── SHACL_rulesetLevel1.ttl
└── tests/                   # logic tests (no GUI required)
```

## Requirements

* Python 3.10+
* This repository's `ifctolbd` package (`pip install -e ..` from here)
* PySide6, PyVista/VTK, pyshacl, ifcopenshell, rdflib

```bash
python -m pip install -e '..[desktop]'
python main.py
```

On Windows (from this folder, with the environment activated):

```bat
py -m pip install -e "..[desktop]"
py main.py
```

## Replicated behaviour

* Menu bar: File/Quit (Ctrl+Q) and Help/About.
* Left rail following the reference application's numbered workflow (Read
  IFC, Settings, Filters, Output, Run, Test, Copy command line).
* Read-in on IFC selection: model statistics are reported in the conversion
  log and the element type / property set inventories feed the **Filters**
  trees. (The Java app's Model Summary card is not shown for now.)
* Workflow status card with elapsed time, indeterminate progress bar, and
  cancel; the conversion itself runs on a background thread.
* Floating, draggable and collapsible cards over the workspace: Settings,
  Filters, Geometry Preview, SPARQL Query, Validate.
* Settings card with Base URI, Product/BOT, Properties/OPM (levels 1-3),
  Geometry, and IfcOWL/Export option groups. Selecting *ifcOWL links* disables
  *Performance mode*, as in the Java app.
* SPARQL Query card executes queries against the latest RDF output (rdflib),
  capped at 1000 rows.
* Validate card loads SHACL shapes (the Java app's level-1 ruleset is bundled
  as the default) and validates each shape separately with pyshacl.
* Geometry Preview renders the OBJ meshes the converter embeds in the RDF
  output (`fog:asObj_v3.0-obj`) using LBD_OBJ_Exporter's PyVista/VTK viewer,
  with automatic framing and rotate/pan/zoom. A software renderer is used when the
  optional PyVista dependencies are unavailable.
  Geometry is enabled by default. Colouring and transparency follow
  [LBD_OBJ_Exporter](https://github.com/jyrkioraskari/LBD_OBJ_Exporter)
  (ported in `obj_exporter.py`): MTL `asMTL_kd` colours are read when present,
  windows render as glass, walls/beams/slabs/doors/roofs/stairs stay opaque,
  and everything else is translucent. The card also has an **Export OBJ**
  button that merges all previewed geometry into a single Wavefront OBJ file,
  as LBD_OBJ_Exporter does.
* Preferences persist between sessions (QSettings, same key names as the Java
  Preferences API usage).

## Differences from the Java app

* Geometry is enabled by default (the Java app defaults it off).
* Conversion is executed by the Python `IFCtoLBDConverter`, so settings the
  Python converter does not implement yet (separate product/property files,
  TriG named graphs, ICDD packages, performance boost, candidate interfaces,
  element wireframes) are shown in the UI and passed through, but currently
  have no effect on the output. ICDD export writes Turtle with a log notice.
* "Copy command line" generates the command for this repository's `ifctolbd`
  CLI instead of the Java `IFCtoLBDConverter_CLI`.
* Property-set filters apply to level-3 property URIs; blank-node (level-2)
  properties cannot be filtered by property set name.
* The 3D preview uses the PyVista/VTK renderer from LBD_OBJ_Exporter instead
  of JavaFX 3D. It supports drag rotation, panning and wheel zoom, and retains
  a software fallback for minimal installations.
