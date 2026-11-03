# 验证证据

- 2026-11-03 B00：真实 git fetch 成功；本地与远端 V1.2 一致 c8be308；main 1f0a3d4；原工作树无改动。
- 新 ZIP SHA256：143b5d4e04f067ab4ccfa216aeafb0a2be0207c64e051d9a24db0639336c505e。解压资料与 ZIP 逐文件比对结果由启动输出保存；包是任务说明与 UI_MOCK，不是已完成功能。
- 已真实读取 README、00/01/02/03/04/07/08/09/10/12，及 05/06/14；检查 runtime_factory/paths、AppShell、ResearchHome、productRoutes、package.json。
- 本轮功能测试尚未运行；历史 V1.2 测试数量不得用于 C 方案验收。
- 未执行任何真实模型研究/财务人工接受/OCR/公开部署；未采购外部服务。调度模型费用由账户计费，未取得实际价格不推算金额。

- B00本轮基础 smoke：`tests/test_parse.py tests/test_demo_pdf.py` 3 PASS/5依赖弃用警告，1.69s（本地Python依赖环境，非真实模型/OCR）。
- M0真实启动spike：`experiments/showcase/runtime_startup_spike.py`，临时全新空runtime、真实缓存 BGE/Milvus，ready 8.682s、health/companies HTTP200、含shutdown总8.704s，LLM调用0。不是完整seed复制或公网性能证据。原始输出 `/tmp/findoc-c-startup-spike.log`。

- B02 worker首候选370e3d0：worker报告build/lint/六张截图+点击流程通过。主控实际读代码并查看Navy1440/Ink1440/Navy390，选择Navy但发现登录/状态流和需求误解，未验收B02。截图路径见reviews交接；原型只是UI_MOCK。
- 模型动态派工：B02初Terra/medium，独立审查后同会话升级Terra/high并重命名“FinDoc C｜M0 首页与登录原型 · 主控修订”；架构评审Astra/ultra。仅记录工具调用配置，不估计计费金额。

- B02主控独立验证于集成5209c8e+最终8c2c8a7补修：Chromium真实HTTP localhost14521，1440/1280/390登录/首页截图、正常登录转场/搜索预填/模式/占用接管确认重置/过期/被接管全部PASS。仅UI_MOCK，无真实auth。主控修复login固定覆盖层下仍挂载工作区的问题，增加登录下不存在sidebar断言；截图位于 `/Users/aipuli/.codex/visualizations/2026/11/03/01a19f9b-6d5d-77d1-92a6-7df1c95f4c96/m0`。
- 主控Node24 build/lint通过，4条fast-refresh警告（含原有测试）及既有bundle>500kB警告；未删警告。
- B01独立评审49e0eba已收取/真实阅读，纳入6项P0合同。不是业务安全验收。
- Git复制工作包原先受text=auto归一CSV行尾，已加限定gitattributes -text并重新staged逐文件与ZIP比对：0差异；原始ZIP保留Downloads。

- M1 U01局部：主控修改AppShell/tokens/shell/productRoutes/Conversations，运行Node24 `productRoutes.test.ts conversationFoundation.test.ts` 6PASS/0skip，旧QA/task/run/report/revision深链保留；预填实际HTTP无POST验证待联调。

- U01预填边界：Chromium拦截API的UI_MOCK三宽1440/1280/390 PASS，question进草稿、未选来源发送禁用、零POST/PATCH/DELETE；脚本frontend/e2e/showcase-entry.mjs，截图m1-entry。不能代替真实服务集成。
- M1 UI首候选171ab87/f14e105/c087b4b已读审：真实接口方向可复用，但正式视觉未延续通过的M0；schema cast、失效时限/晚回epoch等退回Terra/high修订。尚未集成/验收H02/H03/L04。

- H01源a9274f4→集成b5768ee：主控真实读service/api/交接并独立复跑3PASS/ruffPASS（UNIT_FAKE）。runtime_factory唯一接线新增固定代际metadata/已绑定仓储，旧startup/companies/conversation_graph62PASS，14.66s，依赖5warning保留。
- H01真实重依赖装配：修改后startup spike9.607s ready/9.649s含关闭，真实缓存BGE+Milvus，health/companies/dashboard200；空库四KPI0，generation1，独立sample origin=illustrative；LLM0。这只证明真实装配+空库/示意端点，不是财务真人数据/完整seed/auth通过。原始/tmp/findoc-c-dashboard-startup.log。
- L01主控静态发现公开/api代理下pending Cookie path=/demo不匹配，已报后端与独审，必须修复并真实浏览器验。内部TestClient通过不代表外部前缀Cookie可用。

- D01真实公开HTTP预检：四份官方PDF均200，SHA与既有来源manifest一致（美的2024/2025、格力2024/2025），276/219/248/295页；程序封面身份匹配。新副本单独Git忽略目录data/showcase-source-preflight-20261103，无旧数据覆盖/模型调用/真人核准。以前web404/timeout保留，本次直接httpx成功。详情D01_SOURCE_PREFLIGHT.json，不宣称全市场查询/实际导入完成。

## 主控 M1 前端接线复跑

集成9cdc3d5→4bf1bef后，main/ResearchHome接线，`SHOWCASE_TEST_URL=http://127.0.0.1:14521 SHOWCASE_TEST_OUTPUT=/tmp/findoc-root-m1-ui node e2e/showcase-live-mock.mjs`：三宽1440/1280/390完整AppShell登录/首页/指标/退出PASS；错误概览、非法Decimal、到期即时卸载+服务器读回、旧refresh不覆盖新session、未知claim保留并GET恢复PASS。实际Chromium，接口拦截UI_MOCK，LLM0/真实PDF0/真人财务0；截图已由主控打开检查。Node24 build/lint成功，保留chunk/effect/ref/fast-refresh提示。真实HTTP和Cookie验证仍待L03及独立review。

## M1 主控真实页面与独立复核

后端源7f6f268→c826a05，Astra独立review cf5f881→7141ec8。16个目标auth/gateway/reset/dashboard/disclosures tests PASS，ruff PASS，SWIG5warnings保留。主控新增 integrated_http_check.py + showcase-integrated-http.mjs 使用两个独立Chromium进程、实际产品main、真实Vite/gateway/OS child/缓存BGE+Milvus，合成seed（1虚构公司、PDF0/真实事实0/LLM0/真人财务0），验证三宽、pending cookie、旧DTO网关编号、占用/二次owner接管、旧A401及UI卸载、新代恢复公司1、logout reset、seed SHA不变。证据目录uz81ifdo见STATE。首轮oflnrurn因测试未重新填写共享口令等待disabled按钮失败；没有据此修改产品授权条件，修测试后通过。截图另发现index.css全局h1覆盖Hero白色、旧ResearchDashboard全局nav覆盖；视觉修正后将重新检查。
