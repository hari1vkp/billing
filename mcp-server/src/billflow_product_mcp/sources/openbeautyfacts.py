"""Open Beauty Facts adapter - cosmetics & personal care (world.openbeautyfacts.org)."""

from __future__ import annotations

from ..taxonomy import SOURCE_BEAUTY
from .base import BaseProductSource


class OpenBeautyFactsSource(BaseProductSource):
    name = SOURCE_BEAUTY
    host = "world.openbeautyfacts.org"
