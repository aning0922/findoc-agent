"""Public controller factory: python -m uvicorn app.demo.entrypoint:create_app --factory."""
import os
import sys

from app.demo.app import create_demo_app
from app.demo.config import DemoConfig
from app.demo.process import ProcessRuntimeManager


def create_app():
    config = DemoConfig.from_env()
    manager = ProcessRuntimeManager(config, child_mode=os.environ.get("DEMO_CHILD_MODE", "real"),
                                    python=os.environ.get("DEMO_CHILD_PYTHON", sys.executable),
                                    startup_timeout=float(os.environ.get("DEMO_CHILD_STARTUP_TIMEOUT", "90")))
    return create_demo_app(config, manager)
