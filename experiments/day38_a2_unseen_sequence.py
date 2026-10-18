"""
| raw序号 | 输出/跳过/异常 | DocChunk类型 | page | section | text/table_md要点 |
|---:|---|---|---:|---|---|
| 0 | 输出 | paragraph | 1 | None | text原样进来 |
| 1 | 输出 | title | 2 | 第一章 风险管理 | text原样进来 |
| 2 | 输出 | title | 2 | 第一章 风险管理/1.1.1 汇率风险 | text原样进来 |
| 3 | 输出 | paragraph | 2 | 第一章 风险管理/1.1.1 汇率风险 | text原样进来 |
| 4 | 输出 | table | 3 | 第一章 风险管理/1.1.1 汇率风险 | text 用table_caption和table_boy的组合，table_md原样复制table_body |
| 5 | 输出 | title | 3 | 第一章 风险管理/1.2 利率风险 | text原样进来 |
| 6 | 输出 | paragraph | 3 | 第一章 风险管理/1.2 利率风险 | text原样进来 |
| 7 | 输出 | title | 4 | 第二章 经营回顾 | text原样进来 |
| 8 | 输出 | paragraph | 4 | 第二章 经营回顾 | text原样进来 |

| 9 | 异常 | title | 5 | "" |  |



9块

| 最终块序号 | 来自raw序号 | type | page | section | text要点 |
|---:|---:|---|---:|---|---|
| 0 | 0 | paragraphh | 1 | None | text原样进来 |
| 1 | 1 | title | 2 | 第一章 风险管理 | text原样进来 |
| 2 | 2 | title | 2 | 第一章 风险管理/1.1.1 汇率风险 | text原样进来 |
| 3 | 3 | paragraph | 2 | 第一章 风险管理/1.1.1 汇率风险 | text原样进来 |
| 4 | 4 | table | 3 | 第一章 风险管理/1.1.1 汇率风险 | text 用table_caption和table_body组合，如果table_caption为空，用第几页表格+table_body table_md原样复制table_body |
| 5 | 5 | title | 3 | 第一章 风险管理/1.2 利率风险 | text原样进来 |
| 6 | 6 | paragraph | 3 | 第一章 风险管理/1.2 利率风险 | text原样进来 |
| 7 | 7 | title | 4 | 第二章 经营回顾 |  |
| 8 | 8 | paragraph | 4 | 第二章 经营回顾 | text原样进来 |

| 最终块序号 | 来自raw序号 | type | page | section | text要点 |
|---:|---:|---|---:|---|---|
| 0 | 0 | paragraphh | 1 | 未分节 | text原样进来 |
| 1 | 3 | paragraph | 2 | 第一章 风险管理/1.1.1 汇率风险 | 汇率上升会增加美元负债的人民币结算成本。 |
| 2 | 3 | paragraph | 2 | 第一章 风险管理/1.1.1 汇率风险 | 人民币结算成本。汇率下降则可能影响出口收入折算。 |
| 3 | 4 | table | 3 | 第一章 风险管理/1.1.1 汇率风险 | text 用table_caption和table_body组合，如果table_caption为空，用第几页表格+table_body table_md原样复制table_body |
| 4 | 6 | paragraph | 3 | 第一章 风险管理/1.2 利率风险 | text原样进来 |
| 5 | 8 | paragraph | 4 | 第二章 经营回顾 | text原样进来 |

[
  {
    "type": "text",
    "text": "金额单位：人民币万元",
    "text_level": null,
    "page_idx": 0
  },
  {
    "type": "text",
    "text": "第一章 风险管理",
    "text_level": 1,
    "page_idx": 1
  },
  {
    "type": "text",
    "text": "1.1.1 汇率风险",
    "text_level": 3,
    "page_idx": 1
  },
  {
    "type": "text",
    "text": "汇率上升会增加美元负债的人民币结算成本。汇率下降则可能影响出口收入折算。",
    "text_level": null,
    "page_idx": 1
  },
  {
    "type": "table",
    "table_caption": [],
    "table_body": "| 币种 | 敞口 |\n| --- | --- |\n| 美元 | 1200 |",
    "page_idx": 2
  },
  {
    "type": "text",
    "text": "1.2 利率风险",
    "text_level": 2,
    "page_idx": 2
  },
  {
    "type": "text",
    "text": "利率上升会提高融资成本。",
    "text_level": null,
    "page_idx": 2
  },
  {
    "type": "text",
    "text": "第二章 经营回顾",
    "text_level": 1,
    "page_idx": 3
  },
  {
    "type": "text",
    "text": "本期海外收入增长。",
    "text_level": null,
    "page_idx": 3
  }
]

A2首次运行差异：
- 原预测：raw 0 section=None
- 实际：section=""
- 原因：混淆了无章节的两种空值表示
- 分类：表示细节错误，不是内容丢失

"""

from app.rag.parse.mineru_adapter import parse_mineru_output
import app.rag.chunk as chunk_module


long_text = "汇率上升会增加美元负债的人民币结算成本。汇率下降则可能影响出口收入折算。"
id_str_list: list[str] = []


def splitter(text: str) -> list[str]:
    if text == long_text:
        return [
            "汇率上升会增加美元负债的人民币结算成本。",
            "人民币结算成本。汇率下降则可能影响出口收入折算。",
        ]
    return [text]


blocks = parse_mineru_output("experiments/day38_a2_v1", "陌生能源股份_2025年报.pdf")
print("V1 coarse:", blocks)

assert len(blocks) == 9
assert [block.type for block in blocks] == [
    "paragraph",
    "title",
    "title",
    "paragraph",
    "table",
    "title",
    "paragraph",
    "title",
    "paragraph",
]
assert [block.text for block in blocks] == [
    "金额单位：人民币万元",
    "第一章 风险管理",
    "1.1.1 汇率风险",
    "汇率上升会增加美元负债的人民币结算成本。汇率下降则可能影响出口收入折算。",
    "第3页表格\n| 币种 | 敞口 |\n| --- | --- |\n| 美元 | 1200 |",
    "1.2 利率风险",
    "利率上升会提高融资成本。",
    "第二章 经营回顾",
    "本期海外收入增长。",
]
assert [block.page for block in blocks] == [1, 2, 2, 2, 3, 3, 3, 4, 4]
assert [block.section for block in blocks] == [
    "",
    "第一章 风险管理",
    "第一章 风险管理/1.1.1 汇率风险",
    "第一章 风险管理/1.1.1 汇率风险",
    "第一章 风险管理/1.1.1 汇率风险",
    "第一章 风险管理/1.2 利率风险",
    "第一章 风险管理/1.2 利率风险",
    "第二章 经营回顾",
    "第二章 经营回顾",
]

chunk_module.recursive_chunk = splitter

final_blocks = chunk_module.chunk_docment(blocks)
id_str_list = [block.chunk_id for block in final_blocks]

blocks = parse_mineru_output("experiments/day38_a2_v1", "陌生能源股份_2025年报.pdf")
print(blocks)
final_blocks = chunk_module.chunk_docment(blocks)
print(final_blocks)

assert id_str_list == [block.chunk_id for block in final_blocks]

piece1_id = [
    block.chunk_id
    for block in final_blocks
    if block.text == "汇率上升会增加美元负债的人民币结算成本。"
][0]

piece2_id = [
    block.chunk_id
    for block in final_blocks
    if block.text == "人民币结算成本。汇率下降则可能影响出口收入折算。"
][0]

assert piece1_id != piece2_id

assert len(final_blocks) == 6
assert [block.type for block in final_blocks] == [
    "paragraph",
    "paragraph",
    "paragraph",
    "table",
    "paragraph",
    "paragraph",
]
assert [block.page for block in final_blocks] == [1, 2, 2, 3, 3, 4]
assert [block.text for block in final_blocks] == [
    "金额单位：人民币万元",
    "汇率上升会增加美元负债的人民币结算成本。",
    "人民币结算成本。汇率下降则可能影响出口收入折算。",
    "第3页表格\n| 币种 | 敞口 |\n| --- | --- |\n| 美元 | 1200 |",
    "利率上升会提高融资成本。",
    "本期海外收入增长。",
]
assert [block.section for block in final_blocks] == [
    "未分节",
    "第一章 风险管理/1.1.1 汇率风险",
    "第一章 风险管理/1.1.1 汇率风险",
    "第一章 风险管理/1.1.1 汇率风险",
    "第一章 风险管理/1.2 利率风险",
    "第二章 经营回顾",
]

assert all(block.source_file == "陌生能源股份_2025年报.pdf" for block in final_blocks)
assert all(
    block.table_md == "| 币种 | 敞口 |\n| --- | --- |\n| 美元 | 1200 |"
    for block in final_blocks
    if block.type == "table"
)

blocks[4].page = 4
page_changed_blocks = chunk_module.chunk_docment(blocks)
assert page_changed_blocks[3].chunk_id != id_str_list[3]

v2_failed = False

try:
    parse_mineru_output("experiments/day38_a2_v2", "陌生能源股份_2025年报.pdf")
except Exception as exc:
    v2_failed = True
    print("V2 exception:", repr(exc))

assert v2_failed
