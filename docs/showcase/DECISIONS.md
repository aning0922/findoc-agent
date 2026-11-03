# 产品与接口决策

D001 已冻结：V1.2 为唯一开发底座；独立集成工作树；新版工作包取代旧 C 方案。
D002 已冻结：全部 F01–F18，依赖按 36 项 WBS；首屏/典型主路径优先，边缘问题登记 P2。
D003 已冻结并实测：独立 Demo Controller，控制库在 generation 目录外；每代独立子进程 runtime，旧请求固定旧目录，禁止覆盖 SQLite/Milvus 活库。
D004 已冻结：旧 ResearchRun 原文、ACCEPT/SAVE/RESUME、Decimal、revision、旧迁移保持；新增 v2 层。
D005 已择Navy（见D007/D010）：Navy/Blue 与 Ink/Teal 两套统一 token，在同结构 React 原型实际截图后择一。
D006 已冻结：架构/竞态高推理；确定性 UI 中推理；阶段切换重新选择模型与会话名，实际调用结果为证据。

D007 视觉决策（主控独立看图）：370e3d0 的 Navy/Blue 与 Ink/Teal 同结构桌面截图已比较；选 Navy/Blue（深侧栏#111f39、主操作#4878d4、浅背景）。两套图表可读性接近，Navy 的金融研究辨识更强。原型高保真登录与成功流缺口退回修订；B02未完成。手机去除正文后装饰叠层，桌面缩Hero争取y650可见图表。
D008 调度要求不进入产品：用户的“会话改名/模型推理动态切换”指Codex侧边栏开发聊天；FinDoc只显示快速/深度研究与实际业务状态，不新增无关模型设置。

D009 M0冻结：采纳独立49e0eba的6项P0合同修正，API_MINIMUM v1.0为单一研发合同。公共status仅service_state；202 pending/claim；owner step-up五路由+5min限期；OCR artifact/身份评估；时点财务；Findings规范统一kind/text/financial_refs/unresolved_question；job共享预留/UNKNOWN，Memory三代际分离。实际实现验收在各M1–M3，不冒称安全/功能已完成。
D010 B02通过：主控复看最终登录/首页三宽截图并复跑主要点击，选择Navy；登录从独立React视图渲染，不在可聚焦首页上覆盖。原型示意标签保留，默认业务build不包含独立HTML是已知原型范围，正式M1走现有入口。
D011 M0达成后自动M1；无需普通研发许可。正式财务写owner授权之后仍由真人明确三步，不由本代理/测试冒签。

D012 用户明确外部LLM本轮总预算5元人民币；仅主控统一真实调用，shared费用预留ledger不随Demo reset清空。以当日官方DeepSeek峰值cache-miss价格保守预留，UNKNOWN不退，输出token硬限/禁native搜索抓取。probe只是连通证据，不是Agent功能通过。
D013 OCR当前选择Mac本地Apple Vision真实引擎；派生扫描明确标注，版面grid只needs_review不保证表区/行列/合并正确；旧fast及封面准入保留。


## M4／M5 最终冻结补记

- D021：完整公开 seed 独立只读、archive保留原始scope/result/report但不给旧授权；2历史job/2报告3revision、3READY官方PDF与真实OCR，完整双浏览器reset实证。示例note标注预置，不复制财务grants。
- D022：首页默认可开启明确水印的虚构示意财务图；KPI读取真实库存。没有本人核准时不伪造真实公司series或财务比率。
- D023：launcher loopback14530、凭据私有本机文件、TTL20/30、默认wait_only。官方DeepSeek验证受既有5元共享账本约束；sibling .env仅同Git common-dir，不继承任意env到前端。预算不随reset补充。
- D024：报告／研究的来源状态、数据origin、转录审阅、AI解释审阅分别记录。旧任务真人核准不由Agent执行；C02只交给原task等待。
- D025：完整候选交付接受显式human_pending、eval_partial与旧fixture_unavailable；P2独立记录，不将其变更为生产SaaS发布闸门。M0/B02已完成，两套token中Navy/Blue为最终统一方案，前文阶段性“未完成”不再表示当前状态。
