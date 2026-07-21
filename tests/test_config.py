from ifctolbd import ConversionProperties


def test_java_compatible_accessors() -> None:
    props = ConversionProperties()
    assert props.isHasBuildingElements()
    props.setHasBuildingElements(False)
    props.setHasBoundingBoxWKT(True)
    assert not props.has_building_elements
    assert props.hasBoundingBoxWKT()

