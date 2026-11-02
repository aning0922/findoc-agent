# Add persistent financial conversations and explicit research preferences

选择年报后可以在“研究助手”连续追问并重新打开历史。每个会话冻结完整来源身份；模糊或范围外指代先澄清，原文由既有RAG校验返回，财务计算使用服务器恢复的已确认事实及既有Decimal公式。用户单独确认的枚举研究偏好可跨会话使用并可删除。

新增独立Conversation/Memory仓储与追加式v10–v12迁移。操作回执、request hash、数据库running互斥及claim fencing防重放；GET和启动恢复不重发模型。Graph每轮从主表重建有界上下文，摘要不存财务值/偏好正文。旧ResearchRun原文合同、经营任务的ACCEPT/SAVE/RESUME和旧问答深链保持。

验证：完整后端1681PASS/1SKIP（G前快照），G后相关284PASS；前端209PASS/25SKIP，lint/build/audit通过，旧报告83PASS。最终新浏览器21PASS，固定ad12570且0失败/跳过/重试；旧Agent2、QA12、阅读4、报告20、财务边界18、来源失效1均通过。完整快照见tests.md，重复组不相加。真实有限验证有2provider响应、4物理Milvus成功及两原文摘录，GET新增请求0、财务写0；人工语义及真人财务正向旅程待审。

风险/回退：仅本地单人demo，新的自由解释关闭；数据库不自动降级，停服务后使用升级前完整runtime备份或新目录。本PR说明为本地准备文件，尚未创建或提交远程PR。详见release-notes.md和migration.md。
