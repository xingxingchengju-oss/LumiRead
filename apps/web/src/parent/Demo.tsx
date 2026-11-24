import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  json,
  listen,
  message,
  type Mastery,
  type Session,
  type Snapshot,
} from "../api";
import { Archive, Profile } from "./Archive";
import { skills, useResource } from "./data";
import Homework from "./Homework";
import "./demo.css";

const Clouclip = lazy(() => import("./Clouclip"));
type Account = {
  id: string;
  name: string;
  description: string;
  segment: string;
};
type DemoProfile = {
  account_id: string;
  session_id: string;
  learner_id: string;
  learner_hash: string;
  name: string;
  description: string;
  source: string;
  selection: string;
  split: string;
  time_basis: string;
  history: {
    source_order: number;
    original_time: string | null;
    skill: string;
    correct: boolean;
  }[];
};
const sections = {
  overview: "学习概览",
  eye: "护眼观察",
  homework: "作业批改",
  practice: "巩固与错题",
} as const;
type Section = keyof typeof sections;

function Baseline({ profile }: { profile: DemoProfile }) {
  const [expanded, setExpanded] = useState(false);
  const history = profile.history;
  const hasTime = history.some((row) => row.original_time);
  return (
    <section className="paper baseline">
      <h2>起始学习记录</h2>
      <p>
        {profile.source} · {history.length} 次历史作答
      </p>
      <p>{profile.selection}</p>
      <details>
        <summary>查看样本来源</summary>
        <dl className="source-list">
          <div>
            <dt>匿名学习者</dt>
            <dd>
              <code>{profile.learner_hash}</code>
            </dd>
          </div>
          <div>
            <dt>数据划分</dt>
            <dd>{profile.split}</dd>
          </div>
          <div>
            <dt>记录顺序</dt>
            <dd>{profile.time_basis}</dd>
          </div>
        </dl>
      </details>
      {history.length > 0 && (
        <>
          <div
            className="table-clip"
            role="region"
            tabIndex={0}
            aria-label="起始作答明细"
          >
            <table>
              <caption>原始作答序列</caption>
              <thead>
                <tr>
                  <th scope="col">原始顺序</th>
                  <th scope="col">知识点</th>
                  <th scope="col">作答结果</th>
                  {hasTime && <th scope="col">原始时间</th>}
                </tr>
              </thead>
              <tbody>
                {(expanded ? history : history.slice(0, 5)).map((row) => (
                  <tr key={row.source_order}>
                    <td>{row.source_order}</td>
                    <td>{skills[row.skill] || row.skill}</td>
                    <td>{row.correct ? "答对" : "答错"}</td>
                    {hasTime && <td>{row.original_time || "未记录"}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {history.length > 5 && (
            <button
              className="link"
              aria-expanded={expanded}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded
                ? "收起作答序列"
                : "查看全部 " + history.length + " 次作答"}
            </button>
          )}
        </>
      )}
    </section>
  );
}

function Overview({
  profile,
  bus,
}: {
  profile: DemoProfile;
  bus: EventTarget;
}) {
  const mastery = useResource<Mastery>(
    "/learners/" + encodeURIComponent(profile.learner_id) + "/mastery",
    bus,
    "mastery.updated",
  );
  return (
    <div className="overview-grid">
      <div>
        {mastery.error && (
          <p role="alert" className="error">
            {mastery.error}{" "}
            <button className="link" onClick={mastery.reload}>
              重新读取画像
            </button>
          </p>
        )}
        {mastery.data ? (
          <Profile profile={mastery.data} />
        ) : (
          !mastery.error && <p role="status">正在读取学习画像…</p>
        )}
      </div>
      <Baseline profile={profile} />
    </div>
  );
}

function DemoDesk({ profile }: { profile: DemoProfile }) {
  const [section, setSection] = useState<Section>("overview");
  const [bus] = useState(() => new EventTarget());
  const [connection, setConnection] = useState("连接中");
  const snapshot = useResource<Snapshot>(
    "/sessions/" + encodeURIComponent(profile.session_id) + "/snapshot",
    bus,
    "",
  );
  useEffect(() => {
    if (!snapshot.data) return;
    return listen(
      profile.session_id,
      snapshot.data.seq,
      (row) => bus.dispatchEvent(new CustomEvent(row.type, { detail: row })),
      setConnection,
    );
  }, [profile.session_id, bus, snapshot.data]);
  return (
    <main className="demo-body">
      <header className="study-cover">
        <div>
          <p className="cover-account">
            账号 {profile.account_id}　/　{profile.name}
          </p>
          <h1>家庭学习手册</h1>
          <p>{profile.description}</p>
        </div>
      </header>
      <div className="demo-menu">
        <nav aria-label="学习手册目录">
          {Object.entries(sections).map(([id, name]) => (
            <button
              type="button"
              key={id}
              aria-current={section === id ? "page" : undefined}
              onClick={() => setSection(id as Section)}
            >
              {name}
            </button>
          ))}
        </nav>
        <span className="connection" role="status">
          {connection}
        </span>
      </div>
      {snapshot.error && (
        <p role="alert" className="error">
          {snapshot.error} <button onClick={snapshot.reload}>重新连接</button>
        </p>
      )}
      {snapshot.data ? (
        <>
          {section === "overview" && (
            <>
              <Suspense fallback={<p role="status">正在读取护眼记录…</p>}>
                <Clouclip
                  sid={profile.session_id}
                  accountId={profile.account_id}
                  onOpen={() => setSection("eye")}
                />
              </Suspense>
              <Overview profile={profile} bus={bus} />
            </>
          )}
          {section === "eye" && (
            <Suspense fallback={<p role="status">正在打开护眼观察…</p>}>
              <Clouclip
                sid={profile.session_id}
                accountId={profile.account_id}
              />
            </Suspense>
          )}
          {section === "homework" && (
            <Homework
              sid={profile.session_id}
              learner={profile.learner_id}
              bus={bus}
            />
          )}
          {section === "practice" && (
            <Archive
              learner={profile.learner_id}
              bus={bus}
              showProfile={false}
            />
          )}
        </>
      ) : (
        !snapshot.error && <p role="status">正在读取账号记录…</p>
      )}
    </main>
  );
}

export default function Demo() {
  const [profile, setProfile] = useState<DemoProfile | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const channel = useRef<BroadcastChannel | null>(null);
  const pending = useRef(false);
  useEffect(() => {
    document.title = "LumiRead · 家庭学习手册";
    if (!("BroadcastChannel" in window)) return;
    const updates = new BroadcastChannel("lumiread-demo-account");
    channel.current = updates;
    updates.onmessage = () => {
      setConfirm(false);
      setProfile(null);
      setRefresh((n) => n + 1);
    };
    return () => {
      updates.close();
      channel.current = null;
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const readProfile = api<DemoProfile>("/demo/profile", {
      signal: controller.signal,
    }).catch((err: unknown) => {
      if (err instanceof ApiError && [401, 403].includes(err.status))
        return null;
      throw err;
    });
    setLoading(true);
    setError("");
    Promise.all([
      api<{ accounts: Account[] }>("/demo/accounts", {
        signal: controller.signal,
      }),
      readProfile,
    ])
      .then(([list, current]) => {
        if (!controller.signal.aborted) {
          setAccounts(list.accounts);
          setProfile(current);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(message(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [refresh]);
  async function change(
    action: "login" | "reset" | "logout",
    account?: string,
  ) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      if (action === "logout") {
        await api("/demo/logout", { method: "POST" });
        setProfile(null);
      } else {
        const session = await api<Session>(
          "/demo/" + action,
          json(
            "POST",
            action === "reset"
              ? { session_id: profile?.session_id }
              : { account_id: account },
          ),
        );
        setProfile(null);
        const next = await api<DemoProfile>("/demo/profile");
        if (next.session_id !== session.session_id)
          throw new Error("账号已在其他页面切换，请重新读取。");
        setProfile(next);
      }
      setConfirm(false);
      channel.current?.postMessage("changed");
    } catch (err) {
      setError(message(err));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="demo-shell">
      <header className="demo-mast">
        <div className="demo-mast-inner">
          <a
            className="demo-brand"
            href="/showcase"
            aria-label="LumiRead 产品首页"
          >
            <span className="book" aria-hidden="true">
              <i />
              <i />
            </span>
            LumiRead
          </a>
          <nav aria-label="站点导航">
            <a href="/showcase">产品展示</a>
            <a href="/federated">
              联邦学习实验 <span aria-hidden="true">↗</span>
            </a>
          </nav>
        </div>
      </header>
      {error && (
        <div className="demo-error" role="alert">
          {error}{" "}
          <button
            className="link"
            onClick={() => setRefresh((n) => n + 1)}
            disabled={busy}
          >
            重新读取
          </button>
        </div>
      )}
      {loading ? (
        <main role="status">正在读取演示账号…</main>
      ) : profile ? (
        <>
          <div className="account-tools">
            <label>
              切换账号{" "}
              <select
                aria-label="切换账号"
                value={profile.account_id}
                disabled={busy}
                onChange={(e) => void change("login", e.target.value)}
              >
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.id} · {account.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="link"
              disabled={busy}
              onClick={() => setConfirm(!confirm)}
              aria-expanded={confirm}
            >
              重置账号
            </button>
            <button
              className="link"
              disabled={busy}
              onClick={() => void change("logout")}
            >
              退出登录
            </button>
          </div>
          {confirm && (
            <section
              className="reset-confirm"
              role="group"
              aria-label="重置当前账号"
            >
              <div>
                <h2>重置账号 {profile.account_id}？</h2>
                <p>
                  将移除这个账号现场新增的作业、作答、收藏和提醒，恢复起始记录。
                </p>
              </div>
              <button
                className="outline"
                disabled={busy}
                onClick={() => setConfirm(false)}
              >
                取消
              </button>
              <button disabled={busy} onClick={() => void change("reset")}>
                确认重置
              </button>
            </section>
          )}
          <DemoDesk key={profile.session_id} profile={profile} />
        </>
      ) : (
        <main className="account-welcome">
          <div className="account-cover">
            <div>
              <h1>选择演示账号</h1>
              <p>
                用本机公开演示账号登录，查看相应的学习记录。三个账号分别保存现场作业和练习进度。
              </p>
            </div>
          </div>
          {accounts.length > 0 && (
            <div className="login-choices">
              {accounts.map((account) => (
                <article key={account.id} className="login-choice">
                  <span className="initial">{account.id}</span>
                  <span
                    className="login-copy"
                    id={"account-description-" + account.id}
                  >
                    <strong>{account.name}</strong>
                    <small>{account.description}</small>
                  </span>
                  <button
                    className="login-enter"
                    disabled={busy}
                    aria-describedby={"account-description-" + account.id}
                    onClick={() => void change("login", account.id)}
                  >
                    登录 {account.id} <span aria-hidden="true">→</span>
                  </button>
                </article>
              ))}
            </div>
          )}
          {busy && <p role="status">正在打开账号…</p>}
        </main>
      )}
    </div>
  );
}
