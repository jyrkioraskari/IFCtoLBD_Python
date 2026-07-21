from pathlib import Path

import pytest
from rdflib import RDF

from ifctolbd import ConversionProperties, IFCtoLBDConverter
from ifctolbd.namespaces import BOT

SAMPLE = Path(__file__).parents[1] / "examples" / "data" / "two_walls.ifc"


@pytest.mark.parametrize("level", (1, 2, 3))
def test_duplex_conversion(level: int) -> None:
    graph = IFCtoLBDConverter("https://example.org/model/", level).convert(
        SAMPLE, ConversionProperties(export_ifcowl=False)
    )
    assert len(graph) >= 30
    assert len(set(graph.subjects(RDF.type, BOT.Building))) == 1
    assert len(set(graph.subjects(RDF.type, BOT.Element))) == 2


def test_missing_input() -> None:
    with pytest.raises(FileNotFoundError):
        IFCtoLBDConverter().convert("missing.ifc")
