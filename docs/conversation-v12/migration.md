# V1.2 迁移与回退

完整计划见 [migration-plan.md](migration-plan.md)。在原有 v1–v9 后追加三个版本：v10 `conversations_v1`、v11 `research_preferences_v1`、v12 `conversation_summary_v1`。Conversation/Turn/operation/claim fencing 独立于旧 ResearchRun 和 TaskCheckpointer；Memory 当前项、无正文回执及审计独立存放；v12 只保存有界派生结构摘要。

原 v1–v9 的 DDL/checksum 未修改，v10/v11 在提交后也未重写。迁移仍使用现有 BEGIN IMMEDIATE 和逐句 execute，schema/log 失败一起回滚。新库、隔离旧库升级、未知版本/缺失记录/修改 checksum 拒绝和旧记录保留均有测试。

旧 D23 测试去除了“最后版本永远为9”和“未知版本一定是10”的过期假设：保留 v9 精确校验，新增完整 MIGRATIONS 逐项匹配，未知版本改为当前 max+1。失败历史和最终回归分别记录于 [tests.md](tests.md)。

本轮运行均在新隔离 runtime，四份原始年报先核对 product/validation/sources.json SHA256，再只读复制至工作树；正式 runtime、冻结验证原件和旧仓库工作树未用来修改实验。

回退代码不会自动降级数据库。开始前备份 SQLite、PDF 与 Milvus；如需回退至 main，在服务停止后使用升级前完整 runtime 备份，或为 main 新建空目录。不要对已升级库手工删表或改 migration log，也不要把新数据目录直接交给旧版本。删除会话保留操作墓碑以防重放，不级联删除旧 ResearchRun/PDF/已确认财务事实；删除偏好不会修改历史已提交回答或供应商已收到的请求。
