# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportAttributeAccessIssue=false
from FlagEmbedding import BGEM3FlagModel

_model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)


def embed(texts: list[str]) -> list[list[float]]:
    """
    嵌入文本，使用BAAI/bge-m3模型"
    Args:
        texts: 文本列表
    Returns:
        list[list[float]]: 嵌入结果
    """
    out = _model.encode(texts, return_dense=True)
    return [v.tolist() for v in out["dense_vecs"]]
