# M1 Dashboard 任务交接（M0冻结后派工）

H01 新模块owner `app/dashboard/*`、`tests/test_dashboard*`，独立commit；主控唯一装配runtime_factory。H02/H03用通过B02的tokens/组件改为真实DTO渲染，Terra/medium（跨状态高推理）；主控唯一修改ResearchHome/AppShell/产品路由。禁止互相修改同文件。

读取真实SQLiteCompanyRepository/DocumentService/TaskRepository/Report schema/FinancialFactSet query和API_MINIMUM；使用注入依赖或runtime_root只读聚合，不直连原开发库，不让前端常量冒充后端统计。完成研究按有效payload status；报告计头而非revisions；环图同分母。来源失效/版本歧义不显示当前已核准数据。

图表数字Decimal字符串，来源/单位/period/report_year/原文身份逐点可核；默认真实eligible-only，无值为空，独立sample_mode显示虚构企业、界面示意标签且不得生成fact_ref。请求失败不得悄悄显示sample或0。公开预览如实现，仅静态样本，业务API仍需lease。

首页Hero搜索本地目录→选择企业/会话；原型示意数字与产品数据分离。三图tooltip/表格、recent深链、recommend只预填零模型。1440/1280/390真截图；旧深链保留，回归只相关窄集。

用户“会话改名/模型切换”是Codex调度，不给FinDoc添加模型配置。每项交付SHA/验证/截图/真伪与限制。不得部署/合main/修改真实data，不创建额外子会话或subagent。
