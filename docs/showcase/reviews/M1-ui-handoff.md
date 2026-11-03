# M1 UI 工作中交接

分支从 d6ccca07（包含 8c2c8a7）建立。当前仅仪表盘草稿，不可集成验收。Build、lint 通过（lint 有本组件 effect warning）；未做组件截图、浏览器测试或真实后端联调。DemoGate/L04 未实现。

需继续：与 H01 核对 metric_key、comparison 结构及 suggested href 只预填约束；当前柱图是各期对比，不是 comparison DTO；检查 DTO 运行时校验、受控 sample 标识与错误处理；完成三宽截图与测试。Gate 需先确定 202/reset/claim 响应字段和授权错误状态，不可猜测。当前不应接线使用。没有触碰真实数据库或财务操作。
