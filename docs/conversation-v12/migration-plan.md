# V1.2 追加迁移与删除边界

2026-11-02 A0 核实：现有 MIGRATIONS 连续 1–9（report_versions 为9）；版本10预留 Conversation，版本11预留 Memory。后端为这两个schema以及 app/companies/migrations.py 的唯一写入者。

保留1–9的所有DDL和checksum，使用现有 migrate 的 BEGIN IMMEDIATE/execute 逐句追加，不使用 executescript 隐式提交、不删除旧表。新增会话、冻结source、turn、tool event、summary、操作回执及偏好/audit表。所有读写受服务端demo workspace和本地principal约束。

验证必须分别覆盖新库初始化、包含旧迁移及旧ResearchRun的库升级、错误checksum拒绝与事务回滚。正式documents.db、冻结原始PDF、既有验收快照不用于直接迁移实验；使用隔离临时库/SQLite backup副本。

数据库保证每会话至多一条running、operation+请求hash幂等、终态不可改；Service先登记再外部调用，提交后必须读回。启动恢复只处理此前running且运行时归属已独占的记录，不因GET调用恢复或重发模型。

删除会话须单独operation，活动turn时拒绝；仅删除Conversation正文/上下文，保留旧ResearchRun/确认事实/PDF原审计，用户界面明确说明。删除偏好物理清除正文和检索入口，审计/回执不能保存正文或可恢复其内容的payload。其他偏好删除后，新Turn不得从摘要或缓存恢复旧值。旧聊天/历史答案可能仍含用户原话，备份不宣称同步清除。
