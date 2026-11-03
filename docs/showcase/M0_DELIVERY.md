# M0交付（B00/B01/B02完成，M1已启动）

用户可见：可点击React全屏登录、Dashboard Hero/搜索/KPI/折线柱环/近期/推荐、研究上下文及报告/任务预览、占用/确认接管/恢复/超时/下线/空态；全部UI_MOCK显著标签。统一选Navy/Blue，Ink/Teal保留对照。体验 `http://127.0.0.1:14521/showcase.html`（本地Vite进程，重启命令见B02交接）。不是业务认证/财报/模型完成。

分支：codex/findoc-showcase-c-integration；M0闭合 d6ccca07d46f5625bae8176166dc8b9f6e3b434a；wire补充08dcf01。源V1.2 c8be308原分支和数据保留。

实际验证：Git fetch/祖先/干净原树；ZIP逐文件比对无差异；本轮parse/demo PDF3PASS（依赖弃用warnings）；真实缓存BGE+Milvus空临时runtime8.682s ready，health/companies200、LLM0；主控集成树Chromium真实HTTP1440/1280/390截图与正常/占用/接管状态点击PASS、无整体横溢/页面JS错误；Node24 build/lint PASS，fast-refresh及大bundle警告保留。独立审查49e0eba提出6项P0合同，已纳入API_MINIMUM v1.0；没有把静态审查等同隔离安全。

截图：`/Users/aipuli/.codex/visualizations/2026/11/03/01a19f9b-6d5d-77d1-92a6-7df1c95f4c96/m0/`，login/navy三宽与ink1440。浏览器脚本：frontend/e2e/showcase-prototype.mjs。曾失败/退回：初原型误加开发模型设置/无成功登录流/复位转expired；修订后登录覆盖底层工作区；均已修复且保留记录。

合同/owner：独立控制库+每代进程/固定目录、owner5敏感路由、pending/claim；Dashboard计数/来源；OCR artifact+扫描身份；财务时点/Decimal；唯一Findings联合；有界Agent账本/Memory删除。36项在task-board.csv，3项M0完成；M1 L01/H01/H02/H03已派工，其余按依赖待续。root唯一热点接线，三个可见会话并行且动态切模型/名称；orchestration.json保存ID和当前配置。

限制：M1真实双浏览器HTTP/全seed恢复与旧迟到隔离待验证；官方候选web打开404/timeout，不声称下载成功；OCR真实引擎、LLM综合、多Agent、语义记忆、报告PDF待后续。原型入口尚未纳入业务生产build，正式M1将在现有main挂载组件。

费用：未采购外部服务/调用付费业务模型；Codex会话计费无实际价格和用量，不推算金额。未代理真人财务ACCEPT/SAVE/RESUME、未部署/合main/force push/修改真实库。后续普通研发已获用户授权。
