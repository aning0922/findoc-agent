# M2 接力与 owner（2026-11-03）

Integration 已有 D02 controller wiring。后续每条按真实代码实现，不修改旧迁移/事实合同。

## D03（UI visible chat，计划 Terra/medium）

只新增 product/disclosures/DisclosurePanel.tsx + scoped CSS、独立 e2e 和交接；DocumentLibrary/FinancialProduct 由主控接线。读取 reviews/D02-disclosure-handoff.md 真实 DTO。props `{company: string, companies: Company[], onImported?:()=>void}`，允许显示当前所选企业，查询代码/名称与年。产品文案必须“已验证演示目录 · 美的/格力 2024/2025”，不能声称全市场实时发现。publish_date/is_amendment null 显示未知。

搜索只读；明确点击某候选导入，固定 operation UUID，GET imports 只查证不重 POST。completed 只表示上传绑定，不代表解析 READY；调用 onImported 让旧资料目录读回。UNKNOWN 保留原 operation，允许明确只读查询，不自动换 ID；硬 reload 同代保留恢复提示。需要新存储 key 时通知主控与DemoGate owner 纳入精确清理清单；所有请求 abort+epoch 防旧props覆盖新企业。官方URL只以受控返回 href 呈现；不开放任意URL下载代理；旧上传表单为可见回退。所有按钮有动作、390无横溢出。

## O02（OCR visible chat，计划 Terra/high）

先读取 O01_OCR_PREFLIGHT.md/json、experiments/showcase/vision_ocr.swift 和冻结 parse-artifact-v2。真实引擎 Apple Vision 已在 Mac 本机实际运行，不捏造 MinerU/Paddle 可用；不升级锁文件。原生扫描PDF未知，本地测试使用明确标注 derived scan（真实公开年报页的栅格副本，文本层0）。新 app/parsing 独立 v2 服务+库，旧fast/SourceService/prepare合同不变，热点接线主控处理。

推荐独立 artifact 层：固定原 PDF SHA+旧source_revision+attempt+元数据摘要，再绑定 engine/version/adapter/config_hash/output_sha/model_revision unknown 的不可变 artifact。显式POST parse-retry expected_source_revision+operation，GET状态恢复，不从GET启动OCR；重任务有界、代际child停止时终止。每页fast/OCR分流，扫描页实际执行引擎；产物 append-only，failed/partial不能换active完成指针；历史精确artifact可读且标source状态。原图渲染、候选文字与 needs_review 表格/布局输出；严禁伪造 verified geometry。新OCR全文可通过独立有真实索引的v2检索接口读取，明确未做金融确认，不能以旧fast parser_version冒名覆写SourceService/旧Milvus文档集合。

OCR封面身份不能自动越过旧 matches_cover；独立 DocumentIdentityAssessmentV2 pending/manual review，不自动产生任何 local_operator 事实。OCR改错=新artifact，旧引用保留。接口新增字段需先写有限handoff供主控冻结。代表性验证：真实derived scan引擎、页码/文字/preview、同op不重复运行、源修订变化/partial失败保留、旧fast不退化。不因表格分行错位补数字；把真实失败展示出来。

## F01/F02（Sol/high）

已派工。独立 finance_v2 namespace；2原始新指标+可证明的Decimal衍生，不改旧3指标枚举、六事实核对、旧迁移。所有候选/模拟/人工确认分离，主控不会代替真人签核。真实PDF候选带原文页/单位/列标题/来源revision。热点装配由主控。UI F03 等服务确定后接力。
