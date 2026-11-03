"""Read-only showcase dashboard; runtime wiring belongs to the integration owner."""

from app.dashboard.api import create_dashboard_router
from app.dashboard.service import DashboardService

__all__ = ["DashboardService", "create_dashboard_router"]
