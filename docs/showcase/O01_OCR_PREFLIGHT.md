# O01 OCR真实执行预检（尚非O02/O03完成）

本机没有MinerU/PaddleOCR，未修改依赖锁或购买OCR服务。使用macOS内置Apple Vision VNRecognizeTextRequest、accurate、zh-Hans/en-US、revision3，在公开年报真实页的180DPI图像上执行OCR；请求只收到PNG，不收到原文/金额。引擎模型具体revision不由框架暴露，明确unknown。实现源码experiments/showcase/vision_ocr.swift；[官方API文档](https://developer.apple.com/documentation/vision/vnrecognizetextrequest)已实际读取Markdown。

样本来自D01美的2025公开PDF SHA c413ed1b993290ec98b254af4bf6ad69edb5a2230bbaec1b15702119b24d4f5c，物理第9页（印刷第8页）。只读渲染图供引擎；另生成图像-only单页PDF，重新打开验证文本层0字并渲染目检。它是公开文本年报的栅格化衍生扫描样本，不冒充原始扫描披露文件。原PDF不变，所有图/PDF/识别全文都在Git忽略data/showcase-ocr-spike-20261103，不重分发完整资料。

真实识别68行、表区域35行，原生识别约0.741s（不含Swift编译、渲染），候选bbox/置信度已保存。完成OCR后才用原PDF文本做诊断对比，该表27个数字字符串全部能在OCR候选中找到；不等于结构/整页准确率、金融计算或真人核准。单纯bbox行聚类出现8个候选行，换行标签尚未按真实表格网格合并，必须保留needs_review，不声称复杂表格结构已验收。

证据：O01_OCR_PREFLIGHT.json保存引擎/OS/版本/耗时/SHA/页码/限制；本地vision-page-9.json与table-preview.json含全文/bbox，仅供解析预览研发。下一步O02需解析路由/不可变artifact与身份准入，O03原页/表格预览；可保留Apple Vision为macOS本地worker，Linux部署需其它独立OCR worker或预置真实产物，不能宣称云端已支持。

失败/警告：Poppler首次渲染Fontconfig警告（嵌入字体页面目检正常）保留；复杂表格结构未验收。没有LLM调用、没有local_operator财务回执。
