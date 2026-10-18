from app.rag.embed import embed
from experiments.day39_vector_lab import top_k

T1 = "甲公司在2025年度实现营收120亿元。"
T2 = "“营业收入是多少”是一句用于询问金额的中文问句。"
T3 = "乙公司2025年营业收入为120亿元。"
T4 = "甲公司2025年净利润为12亿元。"
T5 = "海豚通过回声定位感知周围环境。"


def test_bge_blackbox():
    query = "甲公司2025年营业收入是多少？"

    documents = [T1, T2, T3, T4, T5]
    document_ids = ["T1", "T2", "T3", "T4", "T5"]

    document_vectors = embed(documents)
    query_vectors = embed([query])

    print(f"文档文本数量：{len(documents)}")
    print(f"文档向量数量：{len(document_vectors)}")
    print(f"文档数量与向量数量一致：{len(documents) == len(document_vectors)}")
    for index, document_vector in enumerate(document_vectors):
        print(f"T{index + 1}的向量维度：{len(document_vector)}")

    query_vector = query_vectors[0]
    print(f"查询向量维度：{len(query_vector)}")
    print(f"查询向量批次 shape：({len(query_vectors)}, {len(query_vector)})")
    print(f"取出的单条查询向量 shape：({len(query_vector)},)")
    candidates = []

    for index, document in enumerate(documents):
        candidates.append(
            {
                "id": document_ids[index],
                "metadata": document,
                "vector": document_vectors[index],
            }
        )
    results = top_k(query_vector, candidates, k=5)

    for index, result in enumerate(results):
        print(
            f"第{index + 1}名：Id: {result['id']}, Text: {result['metadata']}, Score: {result['score']} 向量维度：{len(result['vector'])}"
        )


if __name__ == "__main__":
    test_bge_blackbox()
