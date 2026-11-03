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
