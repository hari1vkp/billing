"""Pluggable external product-catalogue adapters."""

from .base import BaseProductSource, ProductSource, RawExternalProduct, SourceResponse
from .openbeautyfacts import OpenBeautyFactsSource
from .openfoodfacts import OpenFoodFactsSource
from .openproductsfacts import OpenProductsFactsSource
from .registry import get_source, get_sources, source_names

__all__ = [
    "BaseProductSource",
    "ProductSource",
    "RawExternalProduct",
    "SourceResponse",
    "OpenFoodFactsSource",
    "OpenBeautyFactsSource",
    "OpenProductsFactsSource",
    "get_source",
    "get_sources",
    "source_names",
]
