# D01 官方来源预检

2026-11-03，主控使用真实HTTP从公开官方主机下载两家公司2024/2025四份年报，全部200、PDF magic有效、封面公司/年度/年度报告程序匹配、文件SHA与仓库既有来源清单一致。详细URL/页数/字节/SHA见D01_SOURCE_PREFLIGHT.json。新文件在本工作树data/showcase-source-preflight-20261103（Git忽略），原PDF/历史数据未改动，未重分发PDF或发模型。

这解除“只有搜索摘要，官方下载不可用”的不确定性。此前web打开404/timeout保留为失败；本次独立httpx GET成功，不能互相抹掉。已知官方链接可支撑演示期受控目录/下载样例，尚未实现D02目录API/下载器/导入/全市场发现；不存在当前所有公司均可自动查询的声明。

复跑：从仓库根目录以已安装httpx/PyMuPDF的Python执行experiments/showcase/official_sources_spike.py；脚本只读product/validation/sources.json已知官方链接、下载20MiB上限、无重试/不跟重定向、并行2，所有下载均进全新临时目录。它是验证脚本，不是正式SSRF防护下载器。

证据层级PUBLIC_OFFICIAL_PDF_HTTP_NO_LLM，仅真实下载与程序封面身份；不是OCR/解析索引质量、人工财务核准或LLM综合研究。D02可先对两公司四年度建立明显标“已验证演示目录”的候选，不虚称全市场实时搜索；现场官方源失败仍可手动上传。
