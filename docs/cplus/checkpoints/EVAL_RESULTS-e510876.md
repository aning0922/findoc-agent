# C+ 验收证据索引

各表中的PASS限于所写层级。测试条数不等于功能数量；组件/HTTP成功不等于模型答案正确、人类签核或生产验收。原15题历史及固定24题原文未改写。

|场景|实际结果/层级|证据|
|---|---|---|
|T01 公司模糊搜索|PASS：真实名称/代码/拼音候选及浏览器手选市场|M0官方spike、M5-official-reset|
|T02 动态公告|PASS：海尔2025非旧catalog中文/英文分离；接口授权稳定性未知|M1-official-import、M5-official-reset|
|T03 真实下载入库|PASS：官方PDF245页→fast/BGE/Milvus READY，封面身份/元数据独立|M1-official-import|
|T04 cache|PASS：冷下载后新generation跨搜索词cache_hit=true/current binding|M5-official-reset，d7b4160|
|T05 接管与清理|PASS组件组合：两个独立Chrome owner接管旧HTTP401；真实新V3退出后物化/OS退出/GC/公开cache不变；“下载正进行时接管”竞态未在真实浏览器重演|M1-M2-native、M5-official-reset、retired_gc临时fixture|
|T06 三表|PASS限定样本：Gree2024/25各38cells、Midea2025千元列/合并与母公司区分|M1-M2-native、M3-http、真实PDF提取回归|
|T07 本人确认图表|HUMAN_PENDING；候选趋势PASS，不代签|HUMAN_PENDING.md|
|T08 360|PASS候选路线：真实KPI/所选趋势/资料/来源，三宽检查|M1-M2-native、M5-interview|
|T09 财报体检|PASS：三类真实候选程序规则；AI解释BLOCKED_EXTERNAL|M3-http、原生财务路径|
|T10 跨年文本|PASS工具路线：风险/业务/研发三维双侧原文；真实AI解释未过|M5-interview、batch-v3-fixed|
|T11 同行|PASS候选：Gree/Midea2025同期间、Decimal、未知口径拒绝|M3-http、M4/M5-native-exports|
|T12 主营结构|PASS：Gree真实产品/地区收入提取+原生环形；未归一100%|M3-http、M5-interview|
|T13 图表追问|PASS工具路线：2025报告/2024比较期点由服务端cell解析，显式context后提问|M5-point-memory|
|T14 2×2|PASS纯工具：真实四格completed、GET不dispatch，119.413秒；原260秒UNKNOWN保留。非真实LLM多Agent验收|eval/results/batch-v3-fixed、M5-interview|
|T15 OCR|PASS文件转录路线：真实Vision→显式enroll/index/context→OCR引文/bbox；legacyFAILED不改|M1-M2-native|
|T16 混合检索|PASS风险诊断：六道同题同源baseline重现、风险前列原文、30条exact验证；人工precision/MRR未标注，现金流首条不相关失败保留|eval/results/v1/six-query-before-after.md|
|T17 多格式|PASS真实同ref：CSV/XLSX/PPTX可下载且独立打开/渲染、浏览器PDF；权限撤销403且原字节不改|M4-native-exports、M5-native-exports、M5-final-boundary-followup|
|T18 历史/恢复|PASS主路径：真实原operation GET、历史只读、旧会话401、恢复完整V3seed；限定fault/race为fixture|M1-M2-native、M5-official-reset|

## 固定24题

逐题执行层级见 `eval/results/v1/fixed24-execution-tiers.md`；新增Midea2024种子后，E01-02/09工具探针补充见 `eval/results/batch-v3-fixed/fixed24-supplement.json`。这两份是各自执行集，不能把NOT_RUN_BY_THIS_SUITE误读成全项目没有别的证据，也不能反向抹除未执行项。

跨context真实BGE收藏/删除、真实OCR、真实导出/官方来源等组件已有上述实际证据；仍没有完整新真实模型答案PASS，人工语义和金融确认仍待办。完整模型成功分母0，不发布“24题准确率”。精确引用身份与原文字符串匹配不等于结论支持度。

## 最终命令检查点

```sh
PYTHONPATH=. <full-venv-python> -m pytest -q tests/test_cplus_*.py \
  tests/test_demo_auth.py tests/test_demo_gateway.py tests/test_runtime_startup.py \
  tests/test_showcase_local_launcher.py
# 90 passed, 3 skipped, 5 warnings (20.49s)
cd frontend
npm run build
npm run lint
# Node24; exit0; chunk and React/hooks warnings retained
```

3个SKIP为未设置opt-in的真实PDF测试，不算通过；有独立真实公开PDF/HTTP/浏览器结果。此前误写测试文件名exit4、默认Python缺依赖、脚本响应字段/选择器/异步等待错误和首次批次超时分别保留，不以最后一轮PASS覆盖。真实native脚本、环境选项与录屏见RUN_LOCAL/DELIVERY。

费用：同原账本77次，预留1.441018元/5元，UNKNOWN4，实际账单未观察；本轮修复、批次、原文研究和导出0外部模型。无用户财务代签、公开部署或main合并。
