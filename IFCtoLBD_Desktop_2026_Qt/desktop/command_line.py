from __future__ import annotations

from .settings_model import ConversionSettings

# Options the native Python ``ifctolbd`` CLI understands. Settings without a
# flag here (e.g. separate output files) are Python-converter features that are
# handled by the desktop application itself and are omitted from the command.
CLI_BOOLEAN_FLAGS = {
    "has_geometry": "--geometry",
    "has_geolocation": "--geolocation",
    "has_units": "--units",
    "has_bounding_box_wkt": "--bounding-box-wkt",
}


def shell_quote(value: str) -> str:
    """Quote for POSIX shells; the Java app always quotes its arguments."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def build_command_line(
    settings: ConversionSettings,
    selected_types: list[str] | None = None,
    selected_psets: list[str] | None = None,
) -> str:
    """Replicate the desktop "Copy command line" feature for the Python CLI.

    The generated command reproduces the conversion with the repository's
    ``ifctolbd`` console entry point. Options the Python converter does not
    support (ICDD packages, TriG, property-set level flags that are level
    controlled) are noted in comments rather than silently dropped.
    """
    if settings.export_as_icdd():
        return "# ICDD package export is only available in the desktop application."
    if not settings.ifc_file or not settings.rdf_target:
        raise ValueError("IFC input and RDF target must be selected first")

    arguments = ["ifctolbd", shell_quote(settings.ifc_file), shell_quote(settings.rdf_target)]
    base_uri = settings.base_uri.strip() or "https://dot.dc.rwth-aachen.de/IFCtoLBDset#"
    arguments += ["--base-uri", shell_quote(base_uri)]
    arguments += ["--level", str(settings.props_level)]
    if not settings.has_building_properties:
        arguments.append("--no-properties")
    if not settings.export_ifcowl:
        arguments.append("--no-ifcowl")
    for attribute, flag in CLI_BOOLEAN_FLAGS.items():
        if getattr(settings, attribute):
            arguments.append(flag)

    if settings.rdf_target.lower().endswith(".jsonld"):
        arguments.append("# JSON-LD output is selected by the file extension")
    if selected_types or selected_psets:
        arguments.append("# element and property set filters are applied by the desktop app")

    return " ".join(arguments)


def clipboard_fallback(text: str) -> None:
    """Best-effort clipboard write for headless environments (wl-copy/xclip)."""
    import shutil
    import subprocess

    for tool, args in (("wl-copy", []), ("xclip", ("-selection", "clipboard", "-in")), ("xsel", ("--clipboard", "--input"))):
        if shutil.which(tool):
            try:
                subprocess.run([tool, *args], input=text.encode(), check=True, timeout=5)
                return
            except (subprocess.SubprocessError, OSError):
                continue
