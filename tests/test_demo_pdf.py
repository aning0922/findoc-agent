"""用真实新生成文件验证合成输入合同，不调用模型、索引或服务。"""

from pathlib import Path

from app.documents.fast_pdf_parser import parse_fast_pdf_bytes
from app.rag.parse import parse_pdf
from scripts.generate_demo_pdf import generate_demo_pdf


def test_generated_pdf_preserves_facts_pages_and_sources(tmp_path: Path) -> None:
    """检查两次实际生成的文本一致，并分别绑定各自来源路径。"""
    first = generate_demo_pdf(tmp_path / "demo.pdf")
    second = generate_demo_pdf(tmp_path / "demo.pdf")
    expected = {
        1: ("2025年度营业收入：120万元。", "2024年度营业收入：100万元。"),
        2: ("2025年末员工人数：12人。", "本资料未提供员工年龄信息"),
    }
    snapshots = []
    for path in (first, second):
        chunks = parse_pdf(str(path), backend="fast")
        assert {chunk.page for chunk in chunks} == {1, 2}
        assert all(chunk.source_file == str(path) for chunk in chunks)
        for page, facts in expected.items():
            text = "\n".join(chunk.text for chunk in chunks if chunk.page == page)
            assert "合成资料" in text
            assert "完全虚构，仅用于软件演示" in text
            assert f"第{page}页，共2页" in text
            assert all(fact in text for fact in facts)
        snapshots.append([(chunk.page, chunk.type, chunk.text) for chunk in chunks])

    assert snapshots[0] == snapshots[1]
    # 上传解析适配器使用临时路径；对外来源必须恢复为逻辑文件名。
    uploaded = parse_fast_pdf_bytes(first.read_bytes(), first.name)
    assert [(chunk.page, chunk.type, chunk.text) for chunk in uploaded] == snapshots[0]
    assert all(chunk.source_file == first.name for chunk in uploaded)


def test_existing_files_are_preserved_when_versions_are_occupied(tmp_path: Path) -> None:
    """原路径及 v2 已被占用时写入 v3，并核对旧文件字节未变。"""
    original = tmp_path / "demo.pdf"
    version_two = tmp_path / "demo_v2.pdf"
    original.write_bytes(b"existing user file")
    version_two.write_bytes(b"existing version two")
    generated = generate_demo_pdf(original)
    assert generated == tmp_path / "demo_v3.pdf"
    assert original.read_bytes() == b"existing user file"
    assert version_two.read_bytes() == b"existing version two"
    assert {chunk.page for chunk in parse_pdf(str(generated))} == {1, 2}
