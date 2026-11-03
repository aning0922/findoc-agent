# M4 真实候选导出独立检查

范围：只读检查 root 的 `data/cplus-export-native/real-peer.{csv,xlsx,pptx,pdf}` 与 `result.json`，没有修改原工件、查询模型或进行财务确认。来源为公开年报候选；报告域 `peer_comparison_v1`、版本 1，快照 SHA-256 为 `3ce574488a9c9081a70982362967ad574d5778205b20092b564535dee925df49`。各文件实际哈希见 [JSON](m4-evidence/real-artifact-check.json)，CSV/XLSX/PPTX 与 root result.json 一致；PDF 哈希单独记录。

- CSV 共 11 行；目标 `391371999819.49` 在原始及标准化值列以单引号前缀保留文本，状态为 `unconfirmed`；原始证据包含 source_revision 和 physical_page 86。逐字段检查未发现以公式触发字符开头的值。
- XLSX 用 openpyxl 只读重开，含“概览、财务数据、来源证据”三表；财务数据 B2/C2 为字符串 `391371999819.49`，全工作簿公式单元格 0。使用 LibreOffice Calc 另存临时 PDF 验证可以打开，未修改源文件。
- PPTX 用 python-pptx 重开为 6 页，并用 LibreOffice Impress 渲染。使用系统字体配置后六页中文可读；第 3 页是已保存引用页码分布，明确说明不表示财务表现或相关性评分，第 4 页标明候选表格单元转录待核对。六页总览见 [渲染截图](m4-evidence/pptx-six-slides.png)。未见大范围裁切，但第 6 页末行靠近页脚，建议留出更大余量。
- 浏览器打印 PDF 实际 21 页；文本提取可找到目标金额、候选标记、source_revision、physical_page 和完整快照 SHA。首页中文可见，见 [截图](m4-evidence/pdf-page-1.png)。本次没有逐页人工核验 21 页，不能据此宣称全 PDF 无截断。

P2：第 4 页候选表格单元的下方通用说明仍写“OCR转录未经人工核对”；此样本来自财务表格单元提取，建议按引用类型使用准确措辞。第 6 页内容与页脚间距偏小。打印版 21 页且首页使用 field/value 重复行，信息密度和可读性可改善。

渲染环境注意：bundled LibreOffice 默认 fontconfig 指向无有效缓存的配置，初次转换时中文不可见；显式设置 `FONTCONFIG_FILE=/opt/homebrew/etc/fonts/fonts.conf` 后重新渲染中文正常。该现象证明默认环境不能直接作为成功渲染证据，也不能单凭它断言 PPTX 在所有客户端均乱码。原始财报 PDF 数据和二进制工件没有纳入此提交。
