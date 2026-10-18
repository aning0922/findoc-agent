import { verificationText, taskInvalidated } from './researchVerification.ts';
import type { VerificationState } from './researchVerification.ts';
import { researchChapters } from './researchChapters.ts';
import type { Company } from "./api.ts";
import type { Task } from "./operatingResearch.ts";
import { taskLabels } from "./operatingResearch.ts";
import { nextAction } from "./researchJourney.ts";
import styles from "./ResearchJourney.module.css";
import { TaskContextHeader } from './TaskContextHeader.tsx';
import type { ResearchSection } from './productRoutes.ts';
export type Readiness = {
  taskId: string;
  revision: number;
  ready: boolean;
  checked: boolean;
  selected: Record<string, string>;
  next?: { href: string; label: string };
  completed?: number;
  blocked?: boolean;
  verification: VerificationState;
};
export function ResearchTaskHeader({
  task,
  companies,
  unknown,
  busy,
  readiness,
  refresh,
  resume,
  newTask,
  section = 'operating',
  executing = false,
  taskReadState = null,
}: {
  task: Task | null;
  companies: Company[];
  unknown: boolean;
  busy: boolean;
  readiness: Readiness | null;
  refresh: () => void;
  resume: () => void;
  newTask: () => void;
  section?: ResearchSection;
  executing?: boolean;
  taskReadState?: 'checking' | 'unavailable' | null;
}) {
  if (!task) return null;
  const current =
    readiness?.taskId === task.task_id && readiness.revision === task.revision;
  const verification = taskInvalidated(task) ? 'invalidated' : taskReadState || (current ? readiness.verification : 'checking');
  const checked = current && readiness.checked && verification === 'current',
    ready = checked && readiness.ready;
  const stage =
    executing ? 3 : task.status === "completed" ? 4 : task.waiting_checkpoint ? 2 : 3;
  const blocked = verification === 'invalidated';
  const title = verification !== 'current' ? verificationText[verification] : executing ? '正在执行经营研究' : unknown
    ? "执行结果待查证"
    : task.execution_status === "running"
      ? "正在执行研究"
      : blocked
        ? "来源或事实资格失效"
        : task.status === "completed" && checked && !ready
          ? "结果资格待核对"
          : task.status === 'failed'
            ? task.error_code?.startsWith('budget_') ? '研究预算已耗尽' : task.error_code === 'operating_model_unavailable' ? '研究模型连接失败' : '本次研究未取得有效结果'
          : task.status === 'refused' ? '所选资料证据不足'
          : taskLabels[task.status];
  const compact = task.status === "completed" && section !== "sources" && verification === "current";
  return (
    <section className={styles.sticky} aria-label="研究阶段与下一步" data-compact={compact}>
      <TaskContextHeader task={task} companies={companies} unknown={unknown} executing={executing} section={section} verification={verification} compact={compact} />
      {!compact && <details className={styles.stageDetails}>
        <summary>第 {stage + 1}/5 步 · {["研究范围", "准备财报", "核对六项事实", "执行研究", "结果与报告"][stage]}</summary>
        <div className={styles.steps}>
        {["研究范围", "准备财报", "核对六项事实", "执行研究", "结果与报告"].map(
          (label, i) => (
            <span key={label} aria-current={stage === i ? "step" : undefined}>
              {i + 1} · {label}
            </span>
          ),
        )}
      </div>
      </details>}
      <div className={styles.row}>
        <div>
          <h2>
            {title}
          </h2>
          {!compact && <p>
            {verification === 'checking' ? '正在只读复验当前来源与事实。核验完成前暂停金额与引用的使用资格。'
              : verification === 'unavailable' ? '本次读取失败，尚不能确认当前资格；历史保存状态与原身份保留。请只读重新核验，恢复后读取原记录。'
              : executing ? '正在复验六项数据并执行经营研究。停止本页等待后，服务端可能仍在运行。' : unknown
              ? "请只读查证最新结果，避免重复执行。"
              : blocked
                ? "冻结来源无法继续使用。请核对当前来源，并明确建立新研究。"
                : task.waiting_checkpoint && checked
                  ? ready
                    ? "六项已入库且当前有效。复核后明确继续研究。"
                    : `已入库 ${readiness.completed || 0} / 6 项。${readiness.next?.label || "请检查下方失效或冲突项。"}`
                  : nextAction(task)}
          </p>}
        </div>
        <div className={styles.headerActions}>
          {blocked && !unknown && (
            <button
              className="operating-primary"
              disabled={busy}
              onClick={newTask}
            >
              核对新来源并新建研究
            </button>
          )}
          {!executing && task.waiting_checkpoint && ready && (
            <button
              className="operating-primary"
              disabled={busy || unknown}
              onClick={resume}
            >
              复核并继续研究
            </button>
          )}
          {verification === 'current' && task.waiting_checkpoint &&
            checked &&
            !ready &&
            readiness.next &&
            !unknown && (
              <a className={styles.primary} href={readiness.next.href}>
                {readiness.next.label} →
              </a>
            )}
          {unknown && <a href="#research-recovery">查证最新结果 →</a>}
          <button disabled={busy} onClick={refresh}>
            {verification === 'unavailable' || verification === 'checking' ? '重新核验（只读）' : '刷新状态（只读）'}
          </button>
          <details>
            <summary>更多</summary>
            <button disabled={busy || unknown} onClick={newTask}>
              新建研究
            </button>
          </details>
        </div>
      </div>
      <nav className={styles.chapterNav} aria-label="任务章节">
        {researchChapters(section, task.status).map(chapter => <a key={chapter.id} href={`#${chapter.id}`}>{chapter.label}</a>)}
      </nav>
    </section>
  );
}
