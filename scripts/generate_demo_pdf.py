"""生成固定两页的公开合成资料；仅写新文件，不调用模型或摄取服务。"""

import argparse
from pathlib import Path

import pymupdf


DEFAULT_OUTPUT = Path("artifacts/demo/synthetic_finance_demo.pdf")


def generate_demo_pdf(output: Path = DEFAULT_OUTPUT) -> Path:
    """按固定规格生成 PDF，返回实际路径；重名递增编号，其他写入错误直接报错。

    output 是本地调用者指定的 PDF 路径，不来自模型或上传请求。
    编号仅避免文件名冲突，不表示事实版本；相同规格保持相同事实和页码。
    """
    if output.suffix.lower() != ".pdf":
        raise ValueError("输出路径必须使用 .pdf 扩展名")

    page_lines = (
        (
            "经营摘要：年度营业收入",
            "2025年度营业收入：120万元。",
            "2024年度营业收入：100万元。",
            "金额单位：万元。期间口径：对应完整年度。",
        ),
        (
            "经营摘要：年末员工人数",
            "2025年末员工人数：12人。",
            "人数单位：人。时点口径：2025年末。",
            "本资料未提供员工年龄信息，无法据此确定平均年龄。",
        ),
    )
    with pymupdf.open() as document:
        font = pymupdf.Font("cjk")
        for number, lines in enumerate(page_lines, start=1):
            page = document.new_page(width=595, height=842)
            # 将库自带中文字体嵌入 PDF，不依赖作者或阅读器的系统字体。
            page.insert_font(fontname="demo-cjk", fontbuffer=font.buffer)
            # 标记、事实与页码均位于 fast parser 保留的正文区域内。
            for y, text, size in (
                (92, "合成资料：虚构企业甲", 21),
                (125, "完全虚构，仅用于软件演示；不对应真实公司。", 12),
                (180, lines[0], 16),
                (235, lines[1], 14),
                (277, lines[2], 14),
                (335, lines[3], 12),
                (730, f"第{number}页，共2页", 11),
            ):
                page.insert_text((60, y), text, fontname="demo-cjk", fontsize=size)
        document.set_metadata({"title": "合成资料：虚构企业甲经营摘要"})
        document.subset_fonts()
        content = document.tobytes(garbage=4, deflate=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    candidate = output
    version = 2
    while True:
        try:
            # xb 在文件已存在时失败，避免 exists() 后普通写入的覆盖竞争。
            stream = candidate.open("xb")
        except FileExistsError:
            print(f"路径已存在，保留原文件：{candidate}")
            candidate = output.with_name(f"{output.stem}_v{version}{output.suffix}")
            version += 1
            continue
        with stream:
            stream.write(content)
        return candidate


def main() -> None:
    """接受可选 --output 本地路径，打印最终保存位置。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    path = generate_demo_pdf(args.output)
    print(f"已生成合成 PDF：{path}")


if __name__ == "__main__":
    main()
