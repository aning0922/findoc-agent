from pathlib import Path


class LocalObjectStore:
    """只在本地 root 内保存和读取 bytes，不暴露物理路径"""

    def __init__(self, root: Path) -> None:
        """初始化本地对象存储的根目录"""
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve_object_path(self, object_key: str) -> Path:
        """返回 root 内部路径，非法或逃逸 key 抛 ValueError"""
        if not object_key:
            raise ValueError("object_key 不能为空")
        if Path(object_key).is_absolute():
            raise ValueError("object_key 不能为绝对路径")
        key_path = Path(object_key)
        if ".." in key_path.parts:
            raise ValueError("object_key 不能包含 ..")
        candidate = (self._root / key_path).resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError("object_key 不能逃出 _root 的路径")
        return candidate

    def put_bytes(self, object_key: str, content: bytes) -> None:
        """验证object_key
        → 计算内部目标Path
        → 创建目标父目录
        → 写入content
        → 成功时返回None
        Args:
            object_key: 不包含本机绝对路径的逻辑对象定位符。
            content: 需要持久化的原始对象内容。
        Raises:
            ValueError: object_key 不安全或 content 不符合合同。
            OSError: 对象写入失败。
        """
        target_path = self._resolve_object_path(object_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)

    def read_bytes(self, object_key: str) -> bytes:
        """验证object_key
        → 计算内部Path
        → 读取并返回bytes
        主要失败：
            - key 不安全：ValueError；
            - 对象不存在：FileNotFoundError；
            - 读取失败：OSError。

        Args:
            object_key: 不包含本机绝对路径的逻辑对象定位符。
        Returns:
            已保存的原始 bytes。
        Raises:
            ValueError: object_key 不安全。
            FileNotFoundError: 对象不存在。
            OSError: 对象读取失败。
        """
        target_path = self._resolve_object_path(object_key)
        return target_path.read_bytes()
