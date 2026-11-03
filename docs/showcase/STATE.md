# FinDoc C 主控状态

日期：2026-11-03（Asia/Taipei）。目标：F01–F18 求职演示候选；不是生产 SaaS。

- Integration: `codex/findoc-showcase-c-integration`。
- 工作树：`/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent`。
- Git fetch 已执行；V1.2 本地/远端 `c8be30808a3ac8c6d13daa5fd9d43c0ea1212c78`；main `1f0a3d4131480ac0ea742772127afac3c892fc7c`。原 V1.2 保留、工作区干净。
- B00/B01/B02 已完成 M0；M1核心真实HTTP/双浏览器验收通过，完整产品种子仍待E03。
- 主控唯一 owner：runtime_factory.py、migrations.py、DocumentService、AppShell、ResearchHome、Conversations 及产品路由；worker 新文件优先。
- task-board.csv 为 36 项实时表；work-package/data/task_board.csv 为原始不可改参考。
- 会话可见、按当前任务改名；模型/推理在每次派工记录。Astra 架构专项；Terra React 中推理；Sol 后端高推理。
- 当前：M2 真实官方PDF、OCR、扩展财务候选UI已联通；M3 Agent/统一工作区/记忆/报告并行集成。
- 未授权：公开部署、合并 main、force push、真实财务人工接受、覆盖真实数据库、购买服务。

M0完成证据：独立审查源49e0eba（集成5feba0c），UI源370e3d0/0ec4a71（集成6c619c0/5209c8e），主控补修8c2c8a7；API_MINIMUM v1.0纳入六项P0合同。主控在集成工作树复跑1440/1280/390 Chromium+主要点击PASS；build/lint PASS（chunk/fast-refresh警告保留）。本地原型 http://127.0.0.1:14521/showcase.html ，仅UI_MOCK。

M1排程：Sol/high负责L01→L02→L03；Dashboard数据H01独立owner；原UI会话转Terra/medium负责H02/H03新组件+L04界面，遇跨身份状态再high。主控唯一接线AppShell/ResearchHome/main/runtime，独立审查每个SHA。完整seed/reset HTTP/进程验证属于L03/L04 owner，不能用空runtime启动spike代替。

U01主控接线进行中：五导航顺序/中文名、Navy全站tokens、question/company URL仅预填Conversations草稿/资料筛选（不选源/不创建/不发模型）；相关route/conversationFoundation 6PASS。Dashboard与Demo模块待worker交割后接入。

最新调度：H01已集成b5768ee/bfadd8a并独立模块/真实重依赖装配通过；独立认证review dcf6a8f集成2f3223d两P0未关闭；原Dashboard会话转Sol/high做D02官方目录/导入，UI会话Terra/high视觉修订不足后转Sol/high聚焦完整组合布局/负向测试。D01主控f024be2真实官方四PDF通过，D02并行。所有模型/分支/任务状态详CSV+orchestration。

2026-11-03 最新集成：H02/H03/L04 UI9cdc3d5已集成4bf1bef，主控main启用VITE_FINDOC_DEMO_MODE=1时包裹所有入口（默认保留经典模式），ResearchHome接真实Dashboard组件。主控实际AppShell三宽UI_MOCK截图/指标/退出，以及非法overview/Decimal、到期卸载、迟到refresh、UNKNOWN claim只读恢复PASS，截图/tmp/findoc-root-m1-ui。build/lint PASS，chunk、effect/ref和fast-refresh提示保留；尚不代表真实后台登录验收。D02已集成4b36493+f2b7028，14PASS；O01真实Apple Vision spike91cbc67，Mac专用且表结构仍待复核。原D02会话切Astra/high独立复核L03；UI会话Sol/high补跨代存储隔离。

M1后台候选7f6f268已集成c826a05，Astra独立复核cf5f881→7141ec8正式关闭两旧P0；12定点PASS+真实HTTP到期1PASS，真实OS/HTTP/Chromium合成seed。主控真实产品main→Vite /api→controller→真实BGE/Milvus双独立Chromium也PASS：三宽login/home、旧DTO补X-Operation-ID、冲突/owner二次接管、旧A401/业务卸载、新代公司恢复1、logout ready、seed SHA不变（/private/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-integrated-http-uz81ifdo）。首轮test漏填再次共享口令失败保留，修test后PASS；实际截图发现旧CSS标题/导航覆盖，视觉修补后还需复跑截图。后台L03完整产品seed仍未完成。主控16目标tests PASS/ruff。

下一批：原Demo后端会话转Sol/high F01/F02；原review会话转Terra/high O02独立产物；UI Sol/high正在补同代硬reload UNKNOWN提示保留，后转Terra/medium D03。LLM配置当前未知/缺失，已异步询问配置文件路径和小额验证预算，不收聊天密钥；独立研发继续。

M1最终集成89230aa后实跑通过 ex46xvoe：同代硬reload保留UNKNOWN线索、跨代清理mock、真实CSS Hero白色、显式sample图真实端点（虚构数值有水印）、双独立Chromium真实HTTP/real child再通过，LLM0/真实PDF0/真人财务0。精选首页图与结果存档evidence/M1。查看实际390登录封面发现同类h1深色覆盖，主控demo.css补显式white，下一资料导入真实UI轮次复查；不回报该未复查截图完成。

M2资料完整真实UI链已PASS（57iyclvz）：界面建立格力→查2025官方目录→明确导入→下载SHA一致→真实fast解析219页→真实BGE/Milvus READY约40.233秒，PDF1/LLM0/真人财务0/浏览器异常0；三宽目录无溢出。evidence/M2-disclosure存档。前两次harness失败（select可访问名、导航后读取响应体）保留，修交易所aria-label和URL读回后通过；真实登录白色封面已复查。O02已集成b81962f并runtime/policy接线，15目标tests/ruff PASS；独立FTS候选、不改旧fast/Milvus，O03UI进行中。

O03真实HTTP+实际产品UI已PASS isgmzk2o：Midea公开年报第9页派生单页扫描，真实Apple Vision3识别68行/54候选格（17候选行9列），三宽不溢出、GET预览零OCR、显式POST1次、reload只读同artifact；金融0/LLM0/legacy_source_verified=false。evidence/M2-ocr。首轮ayn3q140手机grid撑宽FAIL，主控补grid min-width/minmax/内部scroll后通过，另补大图链接和横向提示。

F01/F02已集成c23c0a8，主控显式真实PDF集3PASS13.31s（fast/不可变证据真实、embed/index假）；4个资产/负债时点候选，未真人确认，正式分析403。F03 UI661f8b4待root审查/接线。M01/M02 backend317d336已集成2db02f8，主控7memory测试及真实BGE语义排序/删除通过，UI未接。新finance owner gate仅私有ASGI marker+当前代trusted header，新增route白名单；共享cost ledger独立于generation。

最新模型配置：用户已完成原仓库.env，授权总费用上限5元人民币。只读4必需项已齐，官方deepseek-flash/api.deepseek.com；密钥不输出/不拷入Git。2026-11-03官方价格峰值cache-miss输入2元/M、输出8元/M作为保守估算，source见provider_budget.py。首个tiny真实probe PASS（input8/output1），不是Agent业务验收；cost ledger data/showcase-cost-control/provider-budget.db，1call保守预留0.004678元，实际账单扣费未观测。所有真实provider验证只由主控统一执行，retry0/max_output<=4096/禁原生SearchFetch，UNKNOWN不退预留，5元到限停止调用但离线研发继续。

主控最新：F03源661f8b4已集成ac69ab5，修正图表按真实日期分组及原始Decimal tooltip；实际三宽Chromium+HTTP+公开部分seed PASS amd4nips。4个真实格力资产/负债候选、两日期、2项待核对review；LLM0/真人确认0，confirmed图正向仍human_pending。evidence/M2-finance。部分只读公开seed含Gree2025真实PDF/1003向量行，complete_product_seed=false，非E03完成。S03已集成14d3994、C01/C02/S01第一组05c7afc，待root运行时接线与真LLM。
