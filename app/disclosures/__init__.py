"""Bounded verified demonstration catalogue, not a live market announcement search."""

from app.disclosures.api import create_disclosure_router
from app.disclosures.service import DisclosureService

__all__ = ["DisclosureService", "create_disclosure_router"]
