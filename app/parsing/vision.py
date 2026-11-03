"""Apple Vision local subprocess. No provider, no financial authority."""

import json
from pathlib import Path
import subprocess
import tempfile


class VisionEngine:
    adapter_version = "apple-vision-swift-v1"
    name = "Apple Vision VNRecognizeTextRequest"

    def __init__(self, *, timeout_seconds=30):
        if not 0 < timeout_seconds <= 60:
            raise ValueError("invalid_vision_timeout")
        self.timeout_seconds = timeout_seconds
        self.script = Path(__file__).with_name("vision_ocr.swift")

    def recognize(self, image: bytes, *, timeout_seconds=None) -> dict:
        with tempfile.TemporaryDirectory(prefix="findoc-vision-") as directory:
            root = Path(directory)
            (root / "page.png").write_bytes(image)
            # Inherits generation process group; stopping runtime retires the worker too.
            subprocess.run(
                ["swift", str(self.script), str(root / "page.png"), str(root / "out.json")],
                check=True,
                timeout=min(self.timeout_seconds, timeout_seconds)
                if timeout_seconds is not None
                else self.timeout_seconds,
                capture_output=True,
            )
            return json.loads((root / "out.json").read_text())
