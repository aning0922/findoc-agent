"""集中保存无需加载生产重依赖即可读取的 runtime 路径常量。"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / "data" / "runtime"
