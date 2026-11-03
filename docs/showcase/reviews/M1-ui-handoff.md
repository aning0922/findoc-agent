# M1 UI 组件交接（最终修订）

基线 `d6ccca07`（包含 `8c2c8a7`），分支 `codex/showcase-h02`。前序 171ab87/f14e105/c087b4b/88b94bc 保留；本次修订覆盖早期草稿的视觉与验证缺口。主控唯一装配，不修改业务热点或锁文件。

## 接线

- `ShowcaseDashboard` 接收 `{companies, company, access?}`，读取 `/api/dashboard/overview` 和 `/api/dashboard/charts?company_id=&metric_key=&sample_mode=`。主控在 ResearchHome 引用即可。显式企业优先；无企业时待 overview 首企业，无目录则显示引导，不请求空公司。
- `DemoGate enabled={显式开关}` 包现有产品；disabled 原样渲染 children。启用时先检查服务与会话，登录/等待/未知申请期间不挂载产品。业务 children 按 `lease_generation` key 重建。前端保护不能替代网关鉴权。
- 正式入口仍未接线；默认 build 包含类型检查但不会把未引用组件打入产品 bundle。真实 HTTP/Cookie/双浏览器权限与 seed 验证留主控接线后的集成阶段。

## 布局与数据

沿用 M0 Navy：Hero 装饰、搜索主 CTA、导入年报/查看研究、四张可点 KPI；2:1 首排趋势/任务环，第二排各期柱图/近期研究，底部推荐。环图 Cell 分色、中心总数与中文状态图例，三图均有表格替代。44px 控件，移动端单列、无装饰图穿正文。

按 H01 a9274f4 对齐：period 为 int，金额有限 Decimal 字符串，真实 fact_ref 对象、revision 与 period 匹配；sample 固定 illustrative-company-a、null source refs 且无 fact_ref。拒绝未知 origin、错误 company/metric/金额形状，不过滤非法点伪装完整序列；不因请求失败切样本或补零。三指标切换；技术标识折叠，来源可进入对应企业资料页。柱图使用同指标各期 points，不冒称跨企业比较。搜索和建议链接只去 `/conversations?company=&question=` 预填。

Gate 校验 status/session/attempt schema 与申请 identity；refresh 用单调请求序列与 generation guard，submit/claim 绑定 epoch，卸载后不接受旧结果。余时到零立即不渲染产品并 GET 核验。claim UUID 与 attempt 不同；未知领取保留原 operation，显式“查询本次申请”仅 GET operations/session，不自动 POST。共享密码与 owner 口令请求后清理；接管重新输入共享密码并确认。财务授权只开放真人核对入口，不自动 ACCEPT/SAVE/RESUME。

## 检查与截图

Node 24 build/lint PASS（已有 fast-refresh、大 chunk 提示及 effect/ref lint warning 保留）。真实 Vite + 本机 Chrome headless，fixture **真正导入 AppShell**，HTTP 全部 Playwright 拦截；meta charset UTF-8，所有截图顶端明确 UI_MOCK。模拟 2 企业/3 年大额数据/3 状态/2 近期/3 推荐，不是真实财报。

PASS：三宽登录+组合首页、指标切换、退出；错误 overview 拒绝 KPI；非法 Decimal 拒绝整图；1 秒到期立即卸载并 GET 核验；旧 refresh 晚回不能覆盖更新 generation；claim 未知不自动重发且只读查询可恢复。截图使用集成分支已选 Navy tokens，未修改本分支旧 shell。已主动 view_image 检查 1440/390 登录和首页。

截图绝对目录：`/Users/aipuli/.codex/visualizations/2026/11/03/01a19f9d-a871-7520-aed9-dd6d22774d1a/m1-final/`，文件 `login-{1440,1280,390}.png`、`home-{1440,1280,390}.png`。

复跑（frontend 目录，先启动 Vite 5180）：

```sh
PATH=/Users/aipuli/.nvm/versions/node/v24.19.0/bin:$PATH npm run dev -- --host 127.0.0.1 --port 5180
# 另一终端；SHOWCASE_TOKENS 可指向待集成版本的 tokens.css，省略则用当前分支样式
CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' SHOWCASE_TOKENS=/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/frontend/src/product/tokens.css node e2e/showcase-live-mock.mjs
```

未运行真实后端鉴权、双浏览器 Cookie、真实 seed/财报/模型、真人财务签核、全量套件或部署。以上 PASS 仅证明组件与模拟合同交互，不是后端权限验收。
