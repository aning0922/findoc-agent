# C+ 本机运行

当前是独立分支的求职展示候选，入口 **http://127.0.0.1:14540**。旧 C 仍在14530，C+独立cookie与data目录。真实来源/候选提取、原文检索、图表、收藏、导出可在不调用外部模型时操作；AI解释不能冒充已生成。

## 此台机器

工作树 `/Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent`。需已有Node24、完整BGE/Milvus Python环境、公开种子bundle/本地模型权重。**Git不包含PDF/向量库/种子二进制，clone后不能直接完整演示。**

私有登录文件为本工作树 `data/showcase-local.env`，权限600且Git忽略，含独立共享密码和所有者密码；在本机查看，勿发到聊天或提交。缺文件时先运行 `scripts/run_showcase_local.py --init-config` 生成私有配置，再本机编辑。默认20分钟、wait_only；`--owner-takeover` 才启用独立所有者密码与二次确认，不开放公共接管。

```sh
cd /Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent
PATH=/Users/aipuli/.nvm/versions/node/v24.19.0/bin:$PATH PYTHONPATH=. \
/Users/aipuli/Documents/AI应用学习/02_项目/findoc-agent/.venv/bin/python scripts/run_showcase_local.py \
  --cplus \
  --seed /Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent/data/showcase-cplus-seed-v3 \
  --export-python /Users/aipuli/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
```

加 `--check` 仅核对依赖/种子/端口，不启动服务。Ctrl+C只停止本launcher拥有的进程。实际运行的是React Vite→独立controller→本代private child→真实PDF/BGE/Milvus；不是离线prototype。

## 种子和恢复

V3本地bundle `data/findoc-showcase-cplus-seed-v3.tar.gz`，SHA-256 `c45d3cb8ec6ffb0d6ff411fe34fdffc9639fc49ad9e1615ed979a1d8dd10355e`；manifest `d96b9340838c1d22619308d5d4492996f99ae03c52bf8a8a17eb6594ca139c3d`。包含格力2024/2025、美的2024/2025、海尔2025共5个READY PDF，以及实际OCR产物/旧FAILED扫描样本和5份历史归档。财务候选文件有5指标10个真实格力点，均未人工核准。

保留原V1 bundle与manifest `efc10a4b48584747130af71ec82171a4e5f766fc53eb1ea92c21fe319e7b3ff4`。V2/V3为追加，不改原文件。退出或接管后物化新generation；候选/问题/偏好/收藏等本代数据不跨代，公开官方PDF cache独立保留。自动GC只删除本controller已确认退出、物化manifest可验证的旧代，保留最近退役代诊断。

新机器需由部署者提供bundle和匹配模型权重，核对SHA后解包到独立data目录；不要覆盖已有数据库。可用 `app.demo.seed.verify_seed(Path(...).resolve())` 检查，脚本 `experiments/cplus/build_additive_seed.py` / `curate_financial_seed.py` 记录来源与追加过程。

## 模型和预算

目前4次C+真实模型尝试均ReadTimeout/UNKNOWN，真实C+AI解释验收未通过。无模型模式展示原文与程序计算，不自动重试UNKNOWN。旧C归档若含旧真实模型结果只作历史展示。

若供应商恢复后需小规模复测，在上方命令增加以下两项（密钥只从部署者私有文件读取）：

```sh
--llm-config /Users/aipuli/Documents/Projects/findoc-agent/.env \
--provider-budget-db /Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/data/showcase-cost-control/provider-budget.db
```

**必须是原同一5元账本，禁止初始化新额度、复制ledger或因generation重置预算。** 当前77物理调用（含原C73）、保守预留1.441018元、UNKNOWN4、账单未观察；预留不等于实际扣费。普通页面GET不调用模型。worker不直接调用provider。

## 导出与平台

CSV无需Excel库；XLSX/PPTX需要 `openpyxl==3.1.5`、`python-pptx==1.0.2`，见根 `requirements-showcase-exports.txt`。可在单独环境安装后把绝对Python路径传 `--export-python`，不用修改旧研发环境。此台已复用现有bundled Python。PPTX实际LibreOffice中文渲染时需系统中文字体/fontconfig；macOS Vision OCR已真跑，Linux OCR未测。

打印版在报告中心打开，浏览器选择另存为PDF；不是服务端PDF截图mock。所有导出绑定domain/id/revision/完整SHA，候选金额保持Decimal文本，下载只返回已保存字节。
