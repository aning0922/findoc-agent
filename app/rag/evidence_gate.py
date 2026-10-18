import math
from dataclasses import dataclass

from app.rag.retriever import SearchHit


@dataclass(frozen=True)
class ConservativeScoreEvidenceGate:
    """职责：
        使用冻结的 top-1 最低分数做生成前保守资格判断。

    输入：
        构造时接收 min_top_score；
        allows 接收 query 和非空有序 SearchHit。

    输出：
        top-1 达到阈值返回 True，否则返回 False。

    边界：
        True 只表示允许进入模型第二层，不代表证据足以回答；
        不调用模型、不修改 hits、不做语义充分性判断。
    """

    min_top_score: float
    """最低得分阈值，低于该值的证据被拒绝"""

    def __post_init__(self) -> None:
        """校验冻结阈值是 cosine 范围内的有限浮点数。

        bool 或非数值抛出 TypeError；NaN、无穷和范围外值抛出 ValueError。
        """

        if isinstance(self.min_top_score, bool) or not isinstance(self.min_top_score, float):
            raise TypeError("最低得分阈值必须是浮点数")
        if not math.isfinite(self.min_top_score):
            raise ValueError("最低得分阈值必须是有限数")
        if self.min_top_score < -1.0 or self.min_top_score > 1.0:
            raise ValueError("最低得分阈值必须大于等于-1且小于等于1")

    def allows(self, query: str, hits: list[SearchHit]) -> bool:
        """query：
            为满足统一 Gate Protocol 保留；
            当前 score-only 策略不读取问题文本。

        hits：
            Retriever 返回的非空有序结果；
            第一个元素就是 top-1。

        返回：
            top-1 score 大于等于阈值时 True，否则 False。

        失败：
            hits 为空或 top-1 score 非有限数时 ValueError。

        边界：
            不修改 hits，不判断事实是否足以回答。
        """
        if not hits:
            raise ValueError("hits 不能为空")
        if not math.isfinite(hits[0].score):
            raise ValueError("hits 的第一个元素的 score 必须是有限数")
        return hits[0].score >= self.min_top_score
