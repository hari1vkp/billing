"""Source registry: resolve source names to adapter instances."""

from __future__ import annotations

from typing import Iterable

from ..taxonomy import ALL_SOURCES
from .base import ProductSource
from .openbeautyfacts import OpenBeautyFactsSource
from .openfoodfacts import OpenFoodFactsSource
from .openproductsfacts import OpenProductsFactsSource

_FACTORIES = {
    "openfoodfacts": OpenFoodFactsSource,
    "openbeautyfacts": OpenBeautyFactsSource,
    "openproductsfacts": OpenProductsFactsSource,
}


def source_names() -> list[str]:
    return list(ALL_SOURCES)


def get_source(name: str) -> ProductSource | None:
    factory = _FACTORIES.get(str(name or "").strip().lower())
    return factory() if factory else None


def get_sources(names: Iterable[str]) -> list[ProductSource]:
    sources: list[ProductSource] = []
    seen: set[str] = set()
    for name in names:
        key = str(name or "").strip().lower()
        if key in seen:
            continue
        source = get_source(key)
        if source is not None:
            sources.append(source)
            seen.add(key)
    return sources
