from math import sqrt


def cosine(a, b) -> float:
    if len(a) != len(b):
        raise ValueError("向量维度不一致")
    if len(a) == 0 or len(b) == 0:
        raise ValueError("向量不能为空向量")
    if all(a[i] == 0 for i in range(len(a))) or all(b[i] == 0 for i in range(len(b))):
        raise ValueError("向量不能为零向量")
    result = sum(a[i] * b[i] for i in range(len(a))) / (
        sqrt(sum(a[i] ** 2 for i in range(len(a)))) * sqrt(sum(b[i] ** 2 for i in range(len(b))))
    )
    if result > 1.0:
        result = 1.0
    if result < -1.0:
        result = -1.0
    return result


def top_k(query, candidates, k) -> list[dict]:
    if not isinstance(k, int):
        raise TypeError("k 必须是整数")
    if k <= 0:
        raise ValueError("k 不能小于等于 0")

    if len(candidates) == 0:
        return []
    result = []
    for candidate in candidates:
        result.append(
            {
                "id": candidate["id"],
                "metadata": candidate["metadata"],
                "vector": candidate["vector"],
                "score": cosine(query, candidate["vector"]),
            }
        )
    result.sort(key=lambda x: x["score"], reverse=True)
    if len(result) < k:
        return result
    return result[:k]
