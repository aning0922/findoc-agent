# FinDoc C 主控状态

日期：2026-11-03（Asia/Taipei）。目标：F01–F18 求职演示候选；不是生产 SaaS。

- Integration: `codex/findoc-showcase-c-integration`。
- 工作树：`/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent`。
- Git fetch 已执行；V1.2 本地/远端 `c8be30808a3ac8c6d13daa5fd9d43c0ea1212c78`；main `1f0a3d4131480ac0ea742772127afac3c892fc7c`。原 V1.2 保留、工作区干净。
- B00/B01/B02 已完成 M0 产品/视觉/最小合同冻结，自动进入 M1（用户已授权）。M1功能尚未验收。
- 主控唯一 owner：runtime_factory.py、migrations.py、DocumentService、AppShell、ResearchHome、Conversations 及产品路由；worker 新文件优先。
- task-board.csv 为 36 项实时表；work-package/data/task_board.csv 为原始不可改参考。
- 会话可见、按当前任务改名；模型/推理在每次派工记录。Astra 架构专项；Terra React 中推理；Sol 后端高推理。
- 后续：独立审查 → UI 原型 → 合同冻结 → M1 Demo/首页并行 → 主控独立审查集成。
- 未授权：公开部署、合并 main、force push、真实财务人工接受、覆盖真实数据库、购买服务。

M0完成证据：独立审查源49e0eba（集成5feba0c），UI源370e3d0/0ec4a71（集成6c619c0/5209c8e），主控补修8c2c8a7；API_MINIMUM v1.0纳入六项P0合同。主控在集成工作树复跑1440/1280/390 Chromium+主要点击PASS；build/lint PASS（chunk/fast-refresh警告保留）。本地原型 http://127.0.0.1:14521/showcase.html ，仅UI_MOCK。

M1排程：Sol/high负责L01→L02→L03；Dashboard数据H01独立owner；原UI会话转Terra/medium负责H02/H03新组件+L04界面，遇跨身份状态再high。主控唯一接线AppShell/ResearchHome/main/runtime，独立审查每个SHA。完整seed/reset HTTP/进程验证属于L03/L04 owner，不能用空runtime启动spike代替。

U01主控接线进行中：五导航顺序/中文名、Navy全站tokens、question/company URL仅预填Conversations草稿/资料筛选（不选源/不创建/不发模型）；相关route/conversationFoundation 6PASS。Dashboard与Demo模块待worker交割后接入。

最新调度：H01已集成b5768ee/bfadd8a并独立模块/真实重依赖装配通过；独立认证review dcf6a8f集成2f3223d两P0未关闭；原Dashboard会话转Sol/high做D02官方目录/导入，UI会话Terra/high视觉修订不足后转Sol/high聚焦完整组合布局/负向测试。D01主控f024be2真实官方四PDF通过，D02并行。所有模型/分支/任务状态详CSV+orchestration。
