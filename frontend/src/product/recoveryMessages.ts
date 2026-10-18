export function qaFailureMessage(code?: string): string {
  const messages: Record<string,string> = {
    llm_error: "模型连接失败，本次没有有效回答。失败记录已保存；请先只读刷新研究历史，确认后可由你重新开始研究。",
    interrupted: "服务执行中断，已保存中断记录，没有有效回答。请先只读查证，需要重新研究时由你明确发起。",
    retrieval_error: "资料检索失败，本次没有有效回答。请只读刷新资料与研究历史，核对来源后再明确开始研究。",
    source_changed: "资料来源发生变化，本次回答未发布。请核对新来源并明确重新开始研究。",
    evidence_validation_error: "原文证据校验未通过，本次没有有效回答。请打开原 PDF 核对资料，确认后再明确开始研究。",
    context_budget_error: "本次问答的上下文预算不足，完整原文无法放入执行范围。没有生成回答；请先只读查看记录，缩小所选资料或问题范围后再明确开始研究。",
    citation_validation_error: "模型返回的引用没有通过核验，本次回答未发布。请先读取失败记录，再决定是否重新研究。",
    execution_error: "研究执行失败，本次没有有效回答。失败记录已保存，请先只读刷新查看，再决定是否重新研究。",
  };
  return messages[code || ""] || "研究失败，未生成有效回答。请先只读刷新研究历史，确认后再明确发起新研究。";
}
export function unsupportedQACalculation(query = ''): boolean {
  return /美元|外币|汇率|换算|跨年|跨年度|合计|加总|总和/.test(query);
}
export function qaRefusalMessage(reason?: string, query = ''): string {
  if (reason === 'requires_confirmed_financial_analysis' && unsupportedQACalculation(query)) return '当前不支持外币换算或跨年度聚合，核对并保存事实不会启用这些计算。可分别提问单年度指标的原值与原单位。';
  if (reason === "requires_confirmed_financial_analysis") return "财务计算需要已确认事实与确定性分析服务。请先核对并入库财务事实，再到财务分析执行计算。";
  if (reason === "unsupported_table_structure") return "表格的年度与金额列关系尚待核验，未发布结构化金额。请打开原 PDF 核对资料。";
  return "所选资料中的证据不足以回答这个问题。请补充资料或调整问题，再由你明确开始研究。";
}
export function researchFailureMessage(code: string): string {
  if (code.startsWith("budget_")) return "本次研究预算已耗尽，没有生成有效研究结果。请查看执行详情，缩小研究范围后明确新建研究。";
  if (["operating_provider_unknown", "interrupted_unknown_execution", "task_save_or_execution_unknown"].includes(code)) return "模型请求或执行结果尚无法确认，本次没有可发布结果。请先按原操作身份只读查证，系统不会自动重发。";
  if (["operating_output_invalid", "operating_model_protocol_failed"].includes(code)) return "模型返回的内容或引用没有通过核验，本次研究失败。请读取失败详情，再决定是否明确新建研究。";
  if (code === "operating_model_unavailable") return "暂时无法连接研究模型，本次没有生成研究结果。请检查模型连接后明确新建研究。";
  return "本次研究没有完成。请先只读查看失败记录，核对资料后再决定是否明确新建研究。";
}

export function qaRefusalTitle(reason?: string, query = ''): string {
  if (reason === 'requires_confirmed_financial_analysis' && unsupportedQACalculation(query)) return '当前不支持这类财务计算';
  if (reason === 'requires_confirmed_financial_analysis') return '当前问题需要已确认财务事实';
  if (reason === 'unsupported_table_structure') return '表格列关系暂未通过核验';
  return '所选资料证据不足';
}
export function qaFailureTitle(code?: string): string {
  if (code === 'llm_error') return '模型连接失败';
  if (code === 'context_budget_error') return '本次问答的处理预算不足';
  if (code === 'source_changed') return '资料来源已变化';
  if (code === 'interrupted') return '本次研究已中断';
  return '本次问答未取得有效回答';
}
