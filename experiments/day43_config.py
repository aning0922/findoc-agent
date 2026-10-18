"""Day43 数据 v2 构建的固定配置。

职责：集中保存构建版本、workspace、文档身份、输入输出路径和 collection 名。
限制：本模块不解析数据、不生成 embedding，也不访问 Milvus。
"""

from pathlib import Path

from typing import TypedDict


class RealDocumentConfig(TypedDict):
    """描述一份真实年报的稳定身份、MinerU 输入和 v2 JSONL 输出位置。"""

    source_file: str
    """源文档文件路径。"""
    document_id: str
    """稳定文档身份。"""
    content_list_file: Path
    """MinerU 输入的 content_list.json 文件路径。"""
    output_jsonl: Path
    """v2 JSONL 输出文件路径。"""


# 当前仓库根目录，用于生成不依赖运行目录的绝对路径。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 本次数据构建的稳定版本，不使用运行时间参与命名。
BUILD_ID = "day43_data_v2"

# 三份演示年报共用的固定 workspace 身份。
DEMO_WORKSPACE_ID = "demo-financial-reports"

# 保存三个 v2 JSONL 和 manifest，不覆盖 data 顶层的 legacy JSONL。
V2_OUTPUT_DIR = PROJECT_ROOT / "data/day43_data_v2"

# Day43 专用 collection，不能改成旧 collection `findoc`。
V2_COLLECTION_NAME = "findoc_day43_v2"


REAL_DOCUMENTS: list[RealDocumentConfig] = [
    RealDocumentConfig(
        source_file="data/成都华微电子2025年报.pdf",
        document_id=("demo-financial-reports:chengdu-huawei-2025-annual-report"),
        content_list_file=(
            PROJECT_ROOT / "mineru_out/成都华微电子2025年报/auto/"
            "成都华微电子2025年报_content_list.json"
        ),
        output_jsonl=V2_OUTPUT_DIR / "成都华微电子2025年报_chunks.jsonl",
    ),
    RealDocumentConfig(
        source_file="data/贵州茅台2025年报.pdf",
        document_id=("demo-financial-reports:kweichow-moutai-2025-annual-report"),
        content_list_file=(
            PROJECT_ROOT / "mineru_out/贵州茅台2025年报/auto/贵州茅台2025年报_content_list.json"
        ),
        output_jsonl=V2_OUTPUT_DIR / "贵州茅台2025年报_chunks.jsonl",
    ),
    RealDocumentConfig(
        source_file="data/京东方A 2025年报.pdf",
        document_id=("demo-financial-reports:boe-a-2025-annual-report"),
        content_list_file=(
            PROJECT_ROOT / "mineru_out/京东方A 2025年报/auto/京东方A 2025年报_content_list.json"
        ),
        output_jsonl=V2_OUTPUT_DIR / "京东方A 2025年报_chunks.jsonl",
    ),
]


# 本次构建清单的固定输出位置。
MANIFEST_PATH = V2_OUTPUT_DIR / "manifest.json"

# Day42 legacy 与 Day43 v2 共用的 embedding 模型。
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"

# BAAI/bge-m3 dense embedding 的固定向量维度。
EMBEDDING_VECTOR_DIM = 1024

# legacy/v2 对照共同使用的向量距离度量。
METRIC_TYPE = "COSINE"

# 保存 legacy 和 v2 collection 的现有 Milvus Lite 数据库。
MILVUS_DB_PATH = PROJECT_ROOT / "data/milvus.db"

# 必须保留且不得被 Day43 构建修改的 legacy collection。
LEGACY_COLLECTION_NAME = "findoc"

# Day43 开始时冻结的 legacy collection 行数。
EXPECTED_LEGACY_ROW_COUNT = 7451
