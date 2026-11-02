# V1.2 HTTP 合同索引

精确字段、nullable/enum、状态与请求hash规则：backend-a0.md第3节，已由contracts.md正式冻结并补充真实PDF路由及“未登记冲突”语义。服务端实际路径不含/api，前端代理统一使用/api。

- Conversation：POST/GET /conversations；GET /conversations/{id}；POST /conversations/{id}/turns；GET /conversations/{id}/turns/by-operation/{op}；GET /conversations/{id}/turns/{turn_id}；DELETE /conversations/{id}；GET /conversation-operations/{op}。保留额外只读创建by-operation便利入口。
- Memory：GET/POST /memories；GET/PATCH/DELETE /memories/{id}；GET /memory-operations/{op}。写操作分别含operation，编辑/删除含expected_revision，保存/修改明确confirmed:true。
- 所有写DTO严格extra=forbid，workspace/principal/revision信任身份从服务器恢复。GET和回执no-store；GET不恢复执行/不调用模型/不补写事实。
- running返回不含候选结果；只有已提交校验终态可返回成功。HTTP200不等于业务answered，必须读取Turn.status/result.kind。source_quote保留旧原文拼接，confirmed_metric/comparison来自确定性服务。
- 模型/源/预算等已登记失败返回安全终态；数据库提交或读回不明503，仅查原operation。明确未登记409可保留草稿后只读刷新；operation_request_conflict和GET404不能作为重POST授权。
- 删除会话不删除旧ResearchRun/PDF/已确认事实/长期偏好；删除偏好不回放旧value，旧回执只保留身份与状态。

接口是否已在实际runtime和浏览器验证，以tests.md的当轮证据为准。
