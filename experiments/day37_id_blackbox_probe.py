
from app.rag.chunk import chunk_docment
from app.rag.parse.models import DocChunk


def make_inputs() -> list[DocChunk]:
    chunks: list[DocChunk] = []
    for i in range(5):
        chunks.append(DocChunk(
            text=f"这是第{i + 1}个段落",
            page = 1,
            section = "",
            source_file = "test.pdf",
            type = "paragraph",
            table_md="",
            chunk_id=""
        ))
    return chunks


def main() -> None:
    chunks1 = make_inputs()
    chunks2 = make_inputs()
    chunks11 = chunk_docment(chunks1)
    chunks22 = chunk_docment(chunks2)

    for c1, c2 in zip(chunks11, chunks22):
        print(f"c1.text: {c1.text}, c2.text: {c2.text} 是否相等：{c1.text == c2.text}")
        print(f"c1.chunk_id: {c1.chunk_id}, c2.chunk_id: {c2.chunk_id} 是否相等：{c1.chunk_id == c2.chunk_id}")
    print(f"chunks11_len: {len(chunks11)}, chunks22_len: {len(chunks22)} 是否相等：{len(chunks11) == len(chunks22)}")
    chunks11_texts = [c.text for c in chunks11]
    chunks22_texts = [c.text for c in chunks22]
    print(f"chunks11_texts: {chunks11_texts} chunks22_texts: {chunks22_texts} 是否相等：{chunks11_texts == chunks22_texts}")
    chunks11_chunk_ids = [c.chunk_id for c in chunks11]
    chunks22_chunk_ids = [c.chunk_id for c in chunks22]
    print(f"第一轮ID是否都非空：{all(c.chunk_id != '' for c in chunks11)}")
    print(f"第二轮ID是否都非空：{all(c.chunk_id != '' for c in chunks22)}")
    print(f"第一轮ID是否全都唯一:{len(chunks11_chunk_ids) == len(set(chunks11_chunk_ids))}")
    print(f"第二轮ID是否全都唯一:{len(chunks22_chunk_ids) == len(set(chunks22_chunk_ids))}")
    print(f"chunks11_chunk_ids: {chunks11_chunk_ids} chunks22_chunk_ids: {chunks22_chunk_ids} 是否相等：{chunks11_chunk_ids == chunks22_chunk_ids}")

if __name__ == "__main__":
    main()