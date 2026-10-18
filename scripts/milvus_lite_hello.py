# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportAttributeAccessIssue=false
from pymilvus import MilvusClient

client = MilvusClient("./data/milvus.db")
client.create_collection(collection_name="demo", dimension=1024, metric_type="COSINE")


def onehot(i: int) -> list[float]:
    """
    onehot编码，将一个整数编码为1024维的向量，其中只有第i个位置为1，其余位置为0
    """
    v = [0.0] * 1024
    v[i] = 1.0
    return v


rows = [{"id": i, "vector": onehot(i), "text": f"块{i}", "page": i + 1} for i in range(5)]
client.insert(collection_name="demo", data=rows)

res = client.search(
    collection_name="demo", data=[onehot(2)], limit=3, output_fields=["text", "page"]
)
for hit in res[0]:
    print(
        f"distance={hit['distance']:.3f} page={hit['entity']['page']} text={hit['entity']['text']}"
    )
