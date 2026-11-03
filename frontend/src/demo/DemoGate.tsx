import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import "./demo.css";

type Session = {
  schema_version: "demo-session-v1";
  state: "active";
  expires_at: string;
  server_now: string;
  remaining_seconds: number;
  lease_generation: number;
  seed_version: string;
  can_review: boolean;
  owner_elevated_until: string | null;
};
type Attempt = {
  operation_id: string;
  state: "pending" | "ready" | "failed" | "claimed" | "cancelled";
  reset_id: string;
  claimable: boolean;
  error_code?: string;
};
type Conflict = {
  code: "occupied";
  message: string;
  remaining_seconds: number;
  expires_at: string;
  takeover_available: boolean;
  lease_generation: number;
};
type Status = {
  service_state: "ready" | "resetting" | "degraded";
  ttl_minutes: number;
  conflict_policy: string;
};
class ApiError extends Error {
  status: number;
  detail: {
    code: string;
    message: string;
    remaining_seconds?: number;
    expires_at?: string;
    takeover_available?: boolean;
    lease_generation?: number;
  };
  constructor(status: number, detail: ApiError["detail"]) {
    super(detail.message);
    this.status = status;
    this.detail = detail;
  }
}
async function request<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`/api/demo${path}`, {
    credentials: "same-origin",
    cache: "no-store",
    signal: AbortSignal.timeout(20000),
    ...(body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new ApiError(
      response.status,
      data.detail || {
        code: "unknown",
        message: `请求失败 (${response.status})`,
      },
    );
  const obj = data as Record<string, unknown>;
  const validSession = () =>
    obj.schema_version === "demo-session-v1" &&
    obj.state === "active" &&
    typeof obj.expires_at === "string" &&
    Number.isFinite(Date.parse(obj.expires_at)) &&
    typeof obj.server_now === "string" &&
    Number.isFinite(Date.parse(obj.server_now)) &&
    typeof obj.remaining_seconds === "number" &&
    Number.isFinite(obj.remaining_seconds) &&
    obj.remaining_seconds > 0 &&
    Number.isInteger(obj.lease_generation) &&
    Number(obj.lease_generation) >= 0 &&
    typeof obj.seed_version === "string" &&
    typeof obj.can_review === "boolean" &&
    (obj.owner_elevated_until === null ||
      typeof obj.owner_elevated_until === "string");
  const validAttempt = () =>
    obj.schema_version === "demo-attempt-v1" &&
    typeof obj.operation_id === "string" &&
    ["pending", "ready", "failed", "claimed", "cancelled"].includes(
      String(obj.state),
    ) &&
    typeof obj.reset_id === "string" &&
    typeof obj.claimable === "boolean";
  if (
    path === "/status" &&
    !(
      obj.schema_version === "demo-status-v1" &&
      ["ready", "resetting", "degraded"].includes(String(obj.service_state)) &&
      typeof obj.ttl_minutes === "number" &&
      [20, 30].includes(obj.ttl_minutes) &&
      ["wait_only", "takeover_enabled"].includes(String(obj.conflict_policy))
    )
  )
    throw new Error("演示状态格式无效");
  if ((path === "/session" || path === "/claim") && !validSession())
    throw new Error("演示会话格式无效");
  if (path.startsWith("/operations/") && !validAttempt())
    throw new Error("申请状态格式无效");
  if (
    (path === "/login" || path === "/takeover") &&
    !(response.status === 202 ? validAttempt() : validSession())
  )
    throw new Error("演示响应格式无效");
  return data as T;
}
const id = () => crypto.randomUUID();
export function DemoGate({
  enabled,
  children,
}: {
  enabled: boolean;
  children: ReactNode;
}) {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [stage, setStage] = useState<
    "checking" | "login" | "active" | "pending"
  >("checking");
  const [message, setMessage] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [owner, setOwner] = useState("");
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [remaining, setRemaining] = useState(0);
  const live = useRef(false);
  const epoch = useRef(0);
  const sequence = useRef(0);
  const generation = useRef(-1);
  const [claimUnknown, setClaimUnknown] = useState(false);
  const claimOperation = useRef("");
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const activate = useCallback((s: Session) => {
    if (!live.current) return;
    if (s.lease_generation < generation.current) return;
    generation.current = s.lease_generation;
    sequence.current++;
    setSession(s);
    setRemaining(s.remaining_seconds);
    setStage("active");
    setPassword("");
    setOwner("");
    setConflict(null);
    setConfirm(false);
    setMessage("");
  }, []);
  const refresh = useCallback(async () => {
    const current = epoch.current;
    const serial = ++sequence.current;
    try {
      const s = await request<Session>("/session");
      if (
        !live.current ||
        current !== epoch.current ||
        serial !== sequence.current ||
        s.lease_generation < generation.current
      )
        return;
      generation.current = s.lease_generation;
      setSession(s);
      setRemaining(s.remaining_seconds);
      setStage("active");
    } catch (e) {
      if (current !== epoch.current || serial !== sequence.current) return;
      const err = e as ApiError;
      epoch.current++;
      setSession(null);
      setStage("login");
      if (err.detail?.code === "expired" || err.detail?.code === "taken_over")
        setMessage(err.message);
      else if (err.status !== 401) setMessage("无法验证演示会话，请重试。");
    }
  }, []);
  useEffect(() => {
    if (!enabled) return;
    live.current = true;
    let alive = true;
    (async () => {
      try {
        const st = await request<Status>("/status");
        if (!alive) return;
        setStatus(st);
        if (st.service_state !== "ready") {
          setStage("login");
          setMessage(
            st.service_state === "degraded"
              ? "演示服务不可用，请稍后再试。"
              : "演示环境正在准备，请稍后再试。",
          );
          return;
        }
        await refresh();
      } catch {
        if (alive) {
          setStage("login");
          setMessage("无法读取演示服务状态，请重试。");
        }
      }
    })();
    return () => {
      alive = false;
      live.current = false;
      epoch.current++;
    };
  }, [enabled, refresh]);
  useEffect(() => {
    if (!enabled || stage !== "active") return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 10000);
    return () => clearInterval(timer);
  }, [enabled, stage, refresh]);
  useEffect(() => {
    if (!enabled || stage !== "active") return;
    const timer = window.setInterval(
      () => setRemaining((x) => Math.max(0, x - 1)),
      1000,
    );
    return () => clearInterval(timer);
  }, [enabled, stage]);
  useEffect(() => {
    if (!enabled || stage !== "pending" || !attempt || claimUnknown) return;
    let cancelled = false;
    const current = epoch.current;
    let timer = 0;
    const poll = async () => {
      try {
        const a = await request<Attempt>(
          `/operations/${encodeURIComponent(attempt.operation_id)}`,
        );
        if (cancelled || current !== epoch.current) return;
        if (a.operation_id !== attempt.operation_id)
          throw new Error("申请身份不匹配");
        if (a.claimable && a.state === "ready") {
          if (!claimOperation.current) claimOperation.current = id();
          const s = await request<Session>("/claim", {
            operation_id: claimOperation.current,
            attempt_operation_id: a.operation_id,
          });
          if (!cancelled && current === epoch.current) activate(s);
          return;
        }
        if (["failed", "cancelled", "claimed"].includes(a.state)) {
          setStage("login");
          setMessage(
            `申请未完成（${a.error_code || a.state}），请等待或联系演示所有者。`,
          );
          return;
        }
        timer = window.setTimeout(poll, 1500);
      } catch {
        if (!cancelled) {
          setClaimUnknown(true);
          setMessage("申请结果暂时未知，请查询本次申请或联系演示所有者。");
        }
      }
    };
    void poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [enabled, stage, attempt, activate, claimUnknown]);
  async function submit(takeover = false) {
    setBusy(true);
    setMessage("");
    const operation_id = id();
    const current = ++epoch.current;
    sequence.current++;
    try {
      const body = takeover
        ? {
            operation_id,
            username,
            password,
            owner_password: owner,
            confirm: true,
            expected_generation: conflict?.lease_generation,
          }
        : { operation_id, username, password };
      const result = await request<Session | Attempt>(
        takeover ? "/takeover" : "/login",
        body,
      );
      if (!live.current || current !== epoch.current) return;
      if ("claimable" in result) {
        if (result.operation_id !== operation_id)
          throw new Error("申请身份不匹配");
        claimOperation.current = "";
        setAttempt(result);
        setPassword("");
        setOwner("");
        setStage("pending");
      } else activate(result);
    } catch (e) {
      if (!live.current || current !== epoch.current) return;
      const err = e as ApiError;
      if (err.status === 423 && err.detail?.code === "occupied")
        setConflict(err.detail as Conflict);
      else setMessage(err.message || "请求失败，请重试。");
    } finally {
      setPassword("");
      setOwner("");
      setBusy(false);
    }
  }
  async function authorize() {
    const current = epoch.current;
    setBusy(true);
    try {
      await request("/owner-authorize", {
        operation_id: id(),
        owner_password: owner,
        confirm: true,
      });
      setOwner("");
      if (!live.current || current !== epoch.current) return;
      await refresh();
      setMessage("已授权人工核对入口；财务确认仍需真人逐步操作。");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setOwner("");
      setBusy(false);
    }
  }
  async function logout() {
    epoch.current++;
    setSession(null);
    setStage("login");
    setBusy(true);
    try {
      await request("/logout", { operation_id: id() });
      setSession(null);
      setStage("login");
      setMessage("已退出，演示环境正在恢复。");
    } catch (e) {
      setSession(null);
      setStage("login");
      setMessage(`退出结果未知：${(e as Error).message}。请联系演示所有者。`);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (enabled && stage === "active" && remaining === 0) {
      epoch.current++;
      setSession(null);
      setStage("checking");
      void refresh();
    }
  }, [enabled, stage, remaining, refresh]);
  if (!enabled) return <>{children}</>;
  if (stage === "checking")
    return (
      <div className="demo-gate" role="status">
        正在验证演示服务…
      </div>
    );
  if (stage === "pending")
    return (
      <div className="demo-gate" role="status">
        <h1>正在准备演示环境</h1>
        <p>等待恢复完成并领取会话，期间不能进入工作区。</p>
        <p>{message}</p>
        {claimUnknown && (
          <button
            onClick={async () => {
              const current = epoch.current;
              try {
                const a = await request<Attempt>(
                  `/operations/${encodeURIComponent(attempt!.operation_id)}`,
                );
                if (
                  !live.current ||
                  current !== epoch.current ||
                  a.operation_id !== attempt!.operation_id
                )
                  return;
                setMessage("已查询本次申请，正在核验会话。");
                const verified = await request<Session>("/session");
                if (live.current && current === epoch.current)
                  activate(verified);
              } catch {
                if (live.current && current === epoch.current)
                  setMessage(
                    "本次申请仍无法查证，已保留原申请，请稍后查询或联系演示所有者。",
                  );
              }
            }}
          >
            查询本次申请
          </button>
        )}
      </div>
    );
  if (stage === "login")
    return (
      <main className="demo-gate demo-login">
        <section className="demo-story">
          <div className="demo-brand">✦ &nbsp; FinDoc.</div>
          <div>
            <small>让资料与研究清晰相连</small>
            <h1>
              让财报研究，
              <br />
              从资料走向<span>洞察。</span>
            </h1>
            <p>在一个清晰的工作空间中，探索资料、梳理问题，并组织研究发现。</p>
            <div className="demo-visual">
              <b>企业研究工作空间</b>
              <p>资料探索　 →　研究分析　 →　报告预览</p>
              <svg viewBox="0 0 500 110">
                <path
                  d="M0 100 L100 75 L180 85 L260 48 L340 60 L420 25 L500 5"
                  fill="none"
                  stroke="#96beff"
                  strokeWidth="4"
                />
              </svg>
            </div>
          </div>
          <small>FinDoc · AI 研究工作空间</small>
        </section>
        <div className="demo-card">
          <h1>欢迎体验 FinDoc</h1>
          <p>演示时长 {status?.ttl_minutes ?? "—"} 分钟，时间由服务器决定。</p>
          {message && <p role="alert">{message}</p>}
          {(!status || status.service_state !== "ready") && (
            <button onClick={() => window.location.reload()}>
              重新检查服务
            </button>
          )}
          {conflict ? (
            <>
              <h2>演示空间正在使用</h2>
              <p>
                {conflict.message} · 剩余 {conflict.remaining_seconds} 秒
              </p>
              <button
                onClick={() => {
                  setConflict(null);
                  setConfirm(false);
                }}
              >
                返回登录
              </button>
              {conflict.takeover_available && (
                <>
                  <label>
                    共享演示密码
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </label>
                  <label>
                    所有者口令
                    <input
                      type="password"
                      value={owner}
                      onChange={(e) => setOwner(e.target.value)}
                    />
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={confirm}
                      onChange={(e) => setConfirm(e.target.checked)}
                    />{" "}
                    我确认结束当前体验并重置演示环境
                  </label>
                  <button
                    disabled={!confirm || !owner || !password || busy}
                    onClick={() => void submit(true)}
                  >
                    确认接管
                  </button>
                </>
              )}
            </>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void submit();
              }}
            >
              <label>
                账号
                <input
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </label>
              <label>
                密码
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>
              <button disabled={busy || status?.service_state !== "ready"}>
                进入演示
              </button>
            </form>
          )}
        </div>
      </main>
    );
  if (!session || remaining === 0)
    return (
      <div className="demo-gate" role="status">
        正在核验会话有效期…
      </div>
    );
  return (
    <div className="demo-active">
      <div className="demo-bar">
        演示会话 · 剩余约 {Math.floor(remaining / 60)}:
        {String(remaining % 60).padStart(2, "0")} ·{" "}
        {session?.can_review ? "已授权人工核对" : "财务核对需所有者授权"}{" "}
        <button disabled={busy} onClick={() => void logout()}>
          退出演示
        </button>
        <details>
          <summary>所有者授权</summary>
          <p>授权仅开放人工核对入口；ACCEPT、SAVE、RESUME 仍须真人逐步确认。</p>
          <label>
            所有者口令
            <input
              type="password"
              value={owner}
              onChange={(e) => setOwner(e.target.value)}
            />
          </label>
          <button disabled={!owner || busy} onClick={() => void authorize()}>
            授权人工核对
          </button>
        </details>
        {message && <span role="status">{message}</span>}
      </div>
      <Fragment key={session?.lease_generation}>{children}</Fragment>
    </div>
  );
}
