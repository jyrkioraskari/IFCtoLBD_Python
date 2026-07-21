import uuid

import pytest

from ifctolbd.guid import compress, expand


@pytest.mark.parametrize(
    ("long_form", "short_form"),
    [
        ("00000000-0000-0000-0000-000000000000", "0000000000000000000000"),
        ("ffffffff-ffff-ffff-ffff-ffffffffffff", "3$$$$$$$$$$$$$$$$$$$$$"),
        ("f70dd363-bfe3-4b93-9d23-795d3947f8a2", "3t3TDZl_DBavqZULqvH$YY"),
    ],
)
def test_ifc_guid_codec(long_form: str, short_form: str) -> None:
    assert compress(long_form) == short_form
    assert expand(short_form) == uuid.UUID(long_form)


def test_rejects_invalid_compressed_guid() -> None:
    with pytest.raises(ValueError):
        expand("not-an-ifc-guid")

