import { useCallback, useEffect, useRef, useState } from "react";
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
  const epoch = useRef(0);
  const claimOperation = useRef("");
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const activate = useCallback((s: Session) => {
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
    try {
      const s = await request<Session>("/session");
      if (current !== epoch.current) return;
      setSession(s);
      setRemaining(s.remaining_seconds);
      setStage("active");
    } catch (e) {
      if (current !== epoch.current) return;
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
    if (!enabled || stage !== "pending" || !attempt) return;
    let cancelled = false;
    let timer = 0;
    const poll = async () => {
      try {
        const a = await request<Attempt>(
          `/operations/${encodeURIComponent(attempt.operation_id)}`,
        );
        if (cancelled) return;
        if (a.claimable && a.state === "ready") {
          if (!claimOperation.current) claimOperation.current = id();
          const s = await request<Session>("/claim", {
            operation_id: claimOperation.current,
            attempt_operation_id: a.operation_id,
          });
          if (!cancelled) activate(s);
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
          setStage("login");
          setMessage("无法恢复申请状态；请等待或联系演示所有者，勿重复申请。");
        }
      }
    };
    void poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [enabled, stage, attempt, activate]);
  async function submit(takeover = false) {
    setBusy(true);
    setMessage("");
    const operation_id = id();
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
      if ("claimable" in result) {
        claimOperation.current = "";
        setAttempt(result);
        setPassword("");
        setOwner("");
        setStage("pending");
      } else activate(result);
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 423 && err.detail?.code === "occupied")
        setConflict(err.detail as Conflict);
      else setMessage(err.message || "请求失败，请重试。");
    } finally {
      setBusy(false);
    }
  }
  async function authorize() {
    setBusy(true);
    try {
      await request("/owner-authorize", {
        operation_id: id(),
        owner_password: owner,
        confirm: true,
      });
      setOwner("");
      await refresh();
      setMessage("已授权人工核对入口；财务确认仍需真人逐步操作。");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
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
      </div>
    );
  if (stage === "login")
    return (
      <main className="demo-gate">
        <div className="demo-card">
          <h1>欢迎体验 FinDoc</h1>
          <p>演示时长 {status?.ttl_minutes ?? "—"} 分钟，时间由服务器决定。</p>
          {message && <p role="alert">{message}</p>}
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
                    disabled={!confirm || !owner || busy}
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
      {children}
    </div>
  );
}
