"""Native Python port of IFCtoLBD's public API."""

from .config import ConversionProperties
from .converter import IFCtoLBDConverter, UnsupportedSchemaError

__version__ = "2.49.0"
__all__ = ["ConversionProperties", "IFCtoLBDConverter", "UnsupportedSchemaError"]

