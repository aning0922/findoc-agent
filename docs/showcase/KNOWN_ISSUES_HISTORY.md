# 已知问题与未验证（主控当前状态）

2026-11-03。完成范围以 task-board.csv 和各固定 SHA 证据为准。

## 当前待完成

- M1/E03：已经验证登录/接管/旧访客下线/代际复位机制；种子仍为1家虚构企业的机制种子，没有完整产品的PDF/会话/报告/研究历史。不得称最终演示环境已经齐备。
- M2：D02提供美的/格力2024/2025四份已验证演示目录，不是全市场实时公告搜索。发布日期/更正状态未查证，API为null。D03前端已完成真实UI官方下载/fast/BGE/Milvus验收，O02已集成；O03已完成真实Vision+产品UI预览，F01/F02两新指标候选已真实PDF验证；F03前端集成/财务真人正向路径待验证。
- OCR：真实Apple Vision（Mac）已跑68行、27/27数字串诊断命中；样本为公开年报真实页的派生扫描，不是原生扫描公告。表格bbox初步聚类分行与原表不全一致，必须needs_review；MinerU/Paddle未安装，Linux可移植执行未验证。
- M3：意图/综合解释/Multi-Agent研发中；语义研究记忆backend已实现并真实BGE验证，UI/Agent接线进行中；报告v2 backend已交割待主控review及真实job适配。旧V1.2能力不等于新增能力完成。
- 外部配置已解决：用户配置原仓库.env，授权runtime API总上限5元。tiny连通probe1call通过，保守预留0.004678元/实际扣费未观测；真实Agent业务尚未跑，不可用probe冒充。root共享预算账本在generation外，其他worker不单独调用付费API。
- human_pending：真实财务ACCEPT/SAVE/RESUME及v2人工签核不能由代理代办；无回执时只展示候选或单独示意数据。未执行财务人工确认、未发布部署、未合main或push。
- P2：Node构建chunk>500KiB、fast-refresh/effect/ref lint提示，PyMuPDF SWIG弃用提示；真实BGE child退出的resource_tracker semaphore提示保留。没有据此扩大生产容灾/性能工作。
- 私有测试集、原始PDF/真实数据库保留，不能复制未知隐私资产进seed或Git。所有当前机制测试均全新临时root。

## 已关闭、保留失败记录

- M1 Cookie Path旧P0：a9284b4/5ea5abb曾在/api浏览器失败；7f6f268改Path=/，Astra cf5f881独立真实Chromium/Vite验证login202→operations200→claim200，关闭。详review/M1-auth-followup-review.md（实际目录reviews）。
- M1 owner grant旧P0：读取body跨5分钟仍转发曾复现；7f6f268读后/转发前重核，独立慢body测试403且upstream0，关闭。
- D01官方链接Web工具404/timeout历史仍在；直接真实HTTP四PDF200/SHA已验证，D02额外真实格力2025下载/fast READY219页通过，fake embed/index，不把早期失败抹除。
- UI初稿曾把开发模型切换误做产品设置、成功流/主布局不足；已退回修订。9cdc3d5正式首页新组件、79e7de6跨代提示及同代硬reload恢复已集成。UI_MOCK不等于真实后台；主控另有实际UI双独立Chromium+真实BGE/Milvus机制seed证据。
- 主控首轮集成UI测试漏重新填写接管共享口令，等待disabled按钮失败；修测试后PASS。实际main样式覆盖Hero白色/导航navy由直接截图发现并修，不将mockfixture通过冒充最终视觉检查。
