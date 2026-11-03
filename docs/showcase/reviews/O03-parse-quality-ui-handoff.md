# O03 解析质量 UI 交接

基线 `5352471932db478b61bf2e22ec4a0092a7f218bb`，分支 `codex/showcase-o03`。主控在资料目录适当位置引用 `ParseQualityPanel({documentId, sourceFile?})`；本分支没有修改 DocumentLibrary、运行时或旧 parser。

明确“打开预览”后 GET parse-identity 和默认 parse-quality；仅“明确开始新解析” POST parse-retry，body 为新 UUID 与服务端 identity 的 expected_source_revision。操作前将 `{documentId,id}` 存 sessionStorage `findoc:parse-operation:<documentId>`，UNKNOWN/网络失败与硬刷新只 GET 原 operation，不自动发起 OCR。该前缀已纳入 Demo 代际清理 allowlist，同有效租约 reload 保留。存储不可用时禁用新解析；可只读预览。

可按 artifact ID 只读查看历史；页面展示 processed/total、OCR 页数、partial/failed、限制、封面 manual_check 与财务未核准。只对 source_status=current 显示受控 image/PDF；stale 历史展示转录/候选格且不借用当前源图。表格逐格按 0 起 row/column 排布，同坐标保留所有 cell，原样展示 text，不补格、不核准；内部横向滚动，明确行列与跨度未知并保留 warning。页面物理页 1 起，校验 cell 原始 text/bbox 与其 source_line_index 对应 lines。当前来源身份匹配不等于财务核准。

Node 24 build/lint PASS（保留既有及组件 effect/ref 提示）；Chrome headless 的拦截假接口在 1440/1280/390 PASS：显式打开预览不 POST、含重复坐标的真实 DTO 形状网格保留全部五格、UNKNOWN 硬刷新后 GET 不重跑、partial/failed 展示、历史 stale 隐藏原图/PDF，页面无横向溢出。模拟图为自绘示意 PNG，非真实原始 PDF/OCR；桌面/390 截图只证明 UI，非 OCR 引擎证据。DemoGate 存储窄集涵盖新增前缀，跨代清理和同代恢复 PASS。原图来源、真实 OCR、与 D02 数据的 HTTP 集成仍由主控接线后验证。

复跑：frontend 下先 `npm run dev -- --host 127.0.0.1 --port 5180`，再 `CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node e2e/showcase-live-parsing.mjs`；storage 窄集 `SHOWCASE_STORAGE_ONLY=1 CHROME_PATH='…' node e2e/showcase-live-mock.mjs`。截图目录 `/Users/aipuli/.codex/visualizations/2026/11/03/01a19f9d-a871-7520-aed9-dd6d22774d1a/o03/`，包括 `grid-*.png`、`unknown-*.png`、`partial-*.png`、`failed-*.png`。O02 的 Apple Vision 实测证据与局限见其交接，不能由本模拟 UI 证明。
