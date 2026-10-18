from math import sqrt


def cosine(x, y) -> float:
    """
    计算两个向量的余弦相似度
    x 和 y 向量不能为空向量或零向量
    x和 y 向量 长度必须一致
    返回值是 float 类型，表示两个向量在多维空间中的夹角余弦值，即两个向量方向上的相似度，
    1：方向相同
    0：方向垂直
    -1：方向相反
    维度不一致、空向量、零向量 → ValueError

    """
    if len(x) != len(y):
        raise ValueError("向量维度不一致")
    if len(x) == 0 or len(y) == 0:
        raise ValueError("向量不能为空向量")
    if all(x[i] == 0 for i in range(len(x))) or all(y[i] == 0 for i in range(len(y))):
        raise ValueError("向量不能为零向量")
    result = sum(x[i] * y[i] for i in range(len(x))) / (
        sqrt(sum(x[i] ** 2 for i in range(len(x)))) * sqrt(sum(y[i] ** 2 for i in range(len(y))))
    )
    if result > 1.0:
        result = 1.0
    if result < -1.0:
        result = -1.0
    return result


def top_k(query, candidates, k) -> list[dict]:
    """
    candidates 中要有 id 字段 metadata 字段 vector 字段
    新结果中要有 id 字段 metadata 字段 vector 字段 score 字段
    新结果按照score 从大到小排列，如果同分按照候选输入顺序排
    不修改原candidates 列表
    k 必须是整数，必须大于零
    如果 k 大于候选数量，返回排序后全部候选，不足k个，返回排序后全部候选
    candidates 为空且 k 合法 → []
    k 不是整数 → TypeError
    k <= 0 → ValueError
    候选向量非法 → 整体抛出 ValueError
    """
    if not isinstance(k, int):
        raise TypeError("k必须是整数")
    if k <= 0:
        raise ValueError("k不能小于等于0")
    if len(candidates) == 0:
        return []
    result = []
    for index, candidate in enumerate(candidates):
        score = cosine(query, candidate["vector"])
        result.append(
            {
                "id": candidate["id"],
                "metadata": candidate["metadata"],
                "vector": candidate["vector"],
                "score": score,
            }
        )
    result.sort(key=lambda x: x["score"], reverse=True)
    if len(result) < k:
        return result
    return result[:k]
