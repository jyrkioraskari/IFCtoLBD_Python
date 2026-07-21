"""FastAPI replacement for the Java/Jersey OpenAPI module."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .converter import IFCtoLBDConverter

try:
    from fastapi import FastAPI, File, Header, HTTPException, UploadFile
    from fastapi.responses import Response
except ImportError as exc:  # fail with an actionable message when this surface is used
    raise RuntimeError("The REST API requires: pip install 'ifctolbd[api]'") from exc

app = FastAPI(title="IFCtoLBD", version="2.49.0")


@app.get("/hello")
def hello() -> str:
    return "OK!"


@app.post("/convertIFCtoLBD")
async def convert_ifc_to_lbd(
    ifcFile: UploadFile = File(...), accept: str = Header("text/turtle"),
) -> Response:
    formats = {
        "application/ld+json": ("json-ld", "ifc2lbd.jsonld"),
        "application/rdf+xml": ("xml", "ifc2lbd.rdf"),
        "text/turtle": ("turtle", "ifc2lbd.ttl"),
    }
    media = accept.split(",", 1)[0].split(";", 1)[0].strip()
    rdf_format, filename = formats.get(media, formats["text/turtle"])
    suffix = Path(ifcFile.filename or "model.ifc").suffix or ".ifc"
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            path = Path(handle.name)
            while chunk := await ifcFile.read(1024 * 1024):
                handle.write(chunk)
        graph = IFCtoLBDConverter("https://dot.dc.rwth-aachen.de/IFCtoLBDset", 3).convert(path)
        body = graph.serialize(format=rdf_format, encoding="utf-8")
        return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if path is not None:
            path.unlink(missing_ok=True)

