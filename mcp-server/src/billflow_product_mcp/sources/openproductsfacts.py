"""Open Products Facts adapter - general/non-food goods (world.openproductsfacts.org)."""

from __future__ import annotations

from ..taxonomy import SOURCE_PRODUCTS
from .base import BaseProductSource


class OpenProductsFactsSource(BaseProductSource):
    name = SOURCE_PRODUCTS
    host = "world.openproductsfacts.org"
