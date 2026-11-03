# C+ M0 可点击 React 预览交接

基线 `45d55d75662f01d9bc78da1a946d845a01a27480`，分支 `codex/cplus-m0-ui`，旧C分支保留。按工作包与离线原型重新用React实现，未使用iframe/注入原HTML，不接后端；所有企业为示例企业A/B虚构，展示数字、指数、图表和文本均 UI_MOCK。页面顶部常驻水印，财务区各处有示意标记。没有读取私有数据库/配置/凭证、没有调用模型。

预览 `frontend/cplus.html`；在frontend运行 `FINDOC_E2E_DISABLE_ENV_FILES=1 npm run dev -- --host 127.0.0.1 --port 5199 --strictPort` 后打开 `/cplus.html`。使用正式main入口不能假设此预览已挂载。一级导航依主控修订为首页、AI研究助手、企业与资料、研究任务、我的报告；企业360/三表/体检/跨年/同行作为企业详情二级入口，AI入口打开批次示意，任务按钮显示未接入提示。业务结构尚未实现，后续企业详情阶段需补。

`CPlusWorkspace({ view, onNavigate, data, onAction })` 是受控入口；`CPlusData` 包含company/peer/companyCode、kpis、series、statements。示例数据只在`cplusPreview.tsx`注入；动作使用onAction回调并显示未接后端提示。当前props是视觉原型合同，不是已冻结API DTO：正式接线需要增加合法企业identity、source revision/年度/财务期间/口径、候选/核准/缺失状态、真实来源页、预算和operation状态，且禁止虚构图表被误当真实图。图表指标选择器当前只切换标签，示例曲线不变；batch/checkup/export只反馈未接入，不创建任务、财务确认或文件。

本地验证：Node24 `npm run build` 和 `npm run lint` exit 0；有既有chunk/lint告警，未当作零告警。Chromium真实渲染但数据/UI均mock，1440/1280/390从首页→企业360→三表切换→体检提示→跨年→同行→批次→导出提示通过、所检查页无水平溢出和pageerror。启动Vite后运行 `node src/product/cplus/smoke.cjs` 可复跑；截图 `/tmp/cplus-home-1440.png`、`/tmp/cplus-home-1280.png`、`/tmp/cplus-home-390.png`，1440/390目视检查。桌面1440首屏可见图表上半区，手机可见水印及搜索CTA。首轮测试因导航装饰图标进入可访问名称而失败，标记aria-hidden后通过。

本轮不是最终产品或真实业务验收。正式导航路由、完整业务结构、同源权限与后端操作、键盘焦点管理/移动抽屉无障碍、真实来源及数据状态、正式图表语义与响应式完整验收均须主控后续完成；没有变更AppShell、路由、Conversations、runtime、依赖或README。
