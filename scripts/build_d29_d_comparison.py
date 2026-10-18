"""Build a same-scene screenshot index from final measured browser artifacts."""
from pathlib import Path
import html
import json

ROOT = Path(__file__).resolve().parents[1] / 'product/d29-d'
before, after = 'before-final', 'after-final-r3'
rows = []
figures = []
for width in (1440, 1024, 390):
    for key, label in [('home', '首页历史入口'), ('midea', '美的首项财务变化'), ('comparison', '双企首项财务变化'), ('report-v1', '报告 v1 首项摘要'), ('report-v2', '报告 v2 首项摘要')]:
        old = json.loads((ROOT / f'evidence/{before}/{key}-{width}-metrics.json').read_text())
        new = json.loads((ROOT / f'evidence/{after}/{key}-{width}-metrics.json').read_text())
        rows.append(f'| {width} | {label} | {old["top"]:.0f} | {new["top"]:.0f} | {new["fontSize"]} |')
        figures.append(f'<section><h2>{html.escape(label)} · {width}</h2><div class="pair">' + ''.join(
            f'<figure><figcaption>{name} · Y={v["top"]:.0f}</figcaption><a href="evidence/{folder}/{key}-{width}.png"><img loading="lazy" src="evidence/{folder}/{key}-{width}.png" alt="{name} {html.escape(label)} {width}"></a></figure>'
            for name, folder, v in [('Before · 固定 C2', before, old), ('After · D29-D', after, new)]) + '</div></section>')
text = '''# D29-D 三视口 Before / After

2026-10-15，Asia/Shanghai。Before 使用 C2 固定 `b9cabd922c5363f3c6ed438a948de98ac0ca8e3d` 的正式产品源码；After 使用本轮正式源码。两者使用相同公开冻结历史、同一视口高度（1440/1024 为 1000，390 为 844）、同样的隔离快照标记和独立 HTTP transport。全部是真实 Chromium 截图，没有绘制替代页面；点击图片可查看原像素。数据是历史读取，不是现场新模型运行，也不证明在新根取得真人财务接受资格。

[完整对照图库](evidence-gallery.html)。Y 为未滚动页面中的绝对 CSS 坐标；首页测主历史入口，结果测首项变化，报告测第一条实际业务摘要。表格是页面测量，不是用户耗时。

| 宽度 | 测量目标 | Before Y | After Y | After 字号 |
|---|---|---:|---:|---|
''' + '\n'.join(rows) + '''

桌面首屏出现实际摘要数值；390 的首条摘要在一次约一屏滚动内可见（Y < 1688）。正文保持 16px，不隐藏语义待审或来源归属。企业、期间在封面可见，详细冻结来源保留展开。手机版目录可折叠，长表只在自身容器横向滚动。1440/1024/390 均断言无全页横向溢出。

首页突出历史成果，空待办缩为一行；没有企业时引导明确建立。单企/双企经营引用卡显示企业、年报、文件、物理页；真实 PDF.js 弹窗、Escape 和返回按钮均恢复触发按钮焦点，新标签辅助入口仍保留。报告下载在三个宽度都逐版本下载两次并核对字节；原 S6 1440/1280/1024 双击协议另由原生集成场景验证。

图片中的外部人工意见是 C2 固定只读证据；原生 pending、经营因果 false、用户编辑待审分别保留。三 CSS 宽度、DOM 字号和键盘操作不能替代原生浏览器 200%、读屏或真实手机，未覆盖清单见 [HUMAN-GATES.md](HUMAN-GATES.md)。
'''
(ROOT / 'BEFORE-AFTER.md').write_text(text)
(ROOT / 'evidence-gallery.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>D29-D 实际 Before / After</title><style>body{font:16px/1.7 system-ui,sans-serif;background:#f4f6f9;color:#172c45;margin:0;padding:24px;max-width:1600px;margin:auto}h1{font-size:28px}section{margin:32px 0}h2{font-size:20px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}figure{margin:0;min-width:0}figcaption{font-weight:600;margin:8px 0}img{display:block;width:100%;height:auto;border:1px solid #ccd5df}@media(max-width:720px){.pair{grid-template-columns:1fr}}</style><h1>D29-D 实际 Before / After</h1><p>固定 C2 → D29-D；公开历史快照与新解析 PDF，未重新运行模型，未重建原生接受资格。点击图片查看原像素。</p>''' + '\n'.join(figures) + '</html>')
print('Built 15 measured scene pairs and an original-image gallery.')
