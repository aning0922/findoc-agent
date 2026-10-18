from collections.abc import Collection, Sequence

RankingCase = tuple[Sequence[str], Collection[str]]


def _validate_k(k: int) -> None:
    """确保 K 是大于等于 1 的整数"""
    if not isinstance(k, int) or isinstance(k, bool):
        raise TypeError("K 必须是整数")
    if k < 1:
        raise ValueError("K 必须大于等于 1")


def _validate_relevant_ids(relevant_ids: Collection[str]) -> None:
    """确保当前指标样本至少标注了一个相关 chunk"""
    if not relevant_ids:
        raise ValueError("relevant_ids 不能为空，当前指标样本没有标注相关 chunk")


def _validate_cases(cases: Sequence[RankingCase]) -> None:
    """确保平均指标包含一个可回答问题"""
    if not cases:
        raise ValueError("cases 不能为空，无法计算平均检索指标")


def hit_at_k(retrieved_ids: Sequence[str], relevant_ids: Collection[str], k: int) -> int:
    """判断当前 k 个检索结果中是否包含至少一个相关 chunk 命中返回 1，否则返回 0

    Args:
        retrieved_ids: 检索结果
        relevant_ids: 相关 chunk 集合
        k: 计算 Hit@K 的 K 值

    Returns:
        int: 是否命中
    """
    _validate_k(k)
    _validate_relevant_ids(relevant_ids)
    for i in range(min(k, len(retrieved_ids))):
        if retrieved_ids[i] in relevant_ids:
            return 1
    return 0


def reciprocal_rank(retrieved_ids: Sequence[str], relevant_ids: Collection[str]) -> float:
    """返回第一个相关 chunk 的排名倒数，没有就返回 0

    Args:
        retrieved_ids: 检索结果
        relevant_ids: 相关 chunk 集合

    Returns:
        float: 第一个相关 chunk 的排名倒数
    """
    _validate_relevant_ids(relevant_ids)
    for i, retrieved_id in enumerate(retrieved_ids):
        if retrieved_id in relevant_ids:
            return 1.0 / (i + 1)
    return 0.0


def mean_hit_at_k(cases: Sequence[RankingCase], k: int) -> float:
    """计算多个可回答问题的平均 Hit@K

    Args:
        cases: 多个可回答问题的检索结果和相关 chunk 集合
        k: 计算 Hit@K 的 K 值

    Returns:
        float: 平均 Hit@K 值
    """
    _validate_k(k)
    _validate_cases(cases)
    return sum(
        hit_at_k(retrieved_ids, relevant_ids, k) for retrieved_ids, relevant_ids in cases
    ) / len(cases)


def mean_reciprocal_rank(cases: Sequence[RankingCase]) -> float:
    """计算多个可回答问题的平均倒数排名

    Args:
        cases: 多个可回答问题的检索结果和相关 chunk 集合

    Returns:
        float: 平均倒数排名值
    """
    _validate_cases(cases)
    return sum(
        reciprocal_rank(retrieved_ids, relevant_ids) for retrieved_ids, relevant_ids in cases
    ) / len(cases)
