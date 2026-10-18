import type { Task } from './operatingResearch.ts';

// Presentation only. These states never grant source, acceptance or publication eligibility.
export type UserStatus = 'waiting' | 'unknown' | 'failed' | 'refused' | 'completed' | 'saved' | 'dirty' | 'invalidated';
export const statusPresentation: Record<UserStatus, { title: string; consequence: string; tone: string }> = {
  waiting: { title: '正在等待结果', consequence: '显示本页实际等待时间；服务端结果尚未读回。', tone: 'warning' },
  unknown: { title: '结果暂时无法确认', consequence: '已保留操作身份。请只读查证，避免重复提交。', tone: 'warning' },
  failed: { title: '本次未取得有效结果', consequence: '请读取失败记录，确认后再明确发起新的尝试。', tone: 'danger' },
  refused: { title: '所选证据不足以回答', consequence: '拒答记录已保留。可调整资料或问题后明确提交。', tone: 'neutral' },
  completed: { title: '研究结果已保存', consequence: '财务、原文与模型解释分别呈现；模型解释仍待人工语义审阅。', tone: 'success' },
  saved: { title: '已保存', consequence: '当前显示服务端读回的保存对象；保存不代表人工语义核准。', tone: 'success' },
  dirty: { title: '当前修改尚未保存', consequence: '请明确保存。浏览、刷新或离开页面不会自动保存。', tone: 'warning' },
  invalidated: { title: '来源或资格已失效', consequence: '历史身份保留。新来源需要重新核对、接受和独立保存。', tone: 'danger' },
};

export function taskUserStatus(task: Task, unknown = false): UserStatus | null {
  if (unknown || task.execution_outcome === 'interrupted/unknown') return 'unknown';
  if (task.publication_eligibility?.status === 'invalidated') return 'invalidated';
  if (task.execution_status === 'running') return 'waiting';
  if (task.status === 'failed') return 'failed';
  if (task.status === 'refused') return 'refused';
  if (task.status === 'completed') return 'completed';
  // Awaiting human confirmation is preparation, not execution or completion.
  return null;
}
