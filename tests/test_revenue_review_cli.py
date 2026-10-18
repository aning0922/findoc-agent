"""CLI 前置门测试：只使用临时路径，不初始化 BGE/Milvus 或确认事实。"""

import argparse
import asyncio
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.agent.revenue_confirmation import RevenueConfirmationError
from scripts import revenue_review


def test_directory_milvus_path_reaches_noninteractive_gate_without_model_or_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "documents.db").touch()
    (tmp_path / "milvus.db").mkdir()
    (tmp_path / "objects").mkdir()
    input_stream = Mock()
    input_stream.isatty.return_value = False
    monkeypatch.setattr(revenue_review.sys, "stdin", input_stream)
    warm = Mock()
    monkeypatch.setattr(revenue_review, "_warm_runtime_bge_before_milvus", warm)
    args = argparse.Namespace(
        runtime_root=tmp_path, output=None, action="confirm", document_id="synthetic"
    )
    with pytest.raises(RevenueConfirmationError, match="interactive_confirmation_required"):
        asyncio.run(revenue_review.run(args))
    warm.assert_not_called()
    input_stream.readline.assert_not_called()


def test_cli_rejects_missing_or_default_runtime_before_initialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    warm = Mock()
    monkeypatch.setattr(revenue_review, "_warm_runtime_bge_before_milvus", warm)
    for root in (tmp_path, revenue_review.DEFAULT_RUNTIME_ROOT, Path("relative")):
        args = argparse.Namespace(runtime_root=root, output=None, action="preview")
        with pytest.raises(RevenueConfirmationError, match="isolated_ready_runtime_required"):
            asyncio.run(revenue_review.run(args))
    warm.assert_not_called()
