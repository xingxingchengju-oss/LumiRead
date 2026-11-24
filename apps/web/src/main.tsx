import { lazy, Suspense, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, ApiError, json, listen, localHost, message } from "./api";
import type { Session, Snapshot } from "./api";
import "./style.css";
const Notebook = lazy(() =>
  import("./parent/Notebook").then((m) => ({ default: m.Notebook })),
);
const Camera = lazy(() =>
  import("./Camera").then((m) => ({ default: m.Camera })),
);
const Showcase = lazy(() => import("./showcase/Showcase"));
const Demo = lazy(() => import("./parent/Demo"));
const Federated = lazy(() => import("./federated/Federated"));

// Existing parent invitations predate the account-based local demo.
if (location.pathname === "/app") {
  const invite = new URLSearchParams(location.hash.slice(1));
  if (
    new URLSearchParams(location.search).has("room") ||
    (invite.has("room") && invite.has("code"))
  ) {
    history.replaceState(
      null,
      "",
      "/legacy-app" + location.search + location.hash,
    );
  }
}
const cameraRoute = location.pathname === "/glasses";
function Brand() {
  return (
    <span className="brand">
      <span className="book" aria-hidden="true">
        <i />
        <i />
      </span>
      LumiRead
    </span>
  );
}
function Pair({ onJoin }: { onJoin: (s: Session) => void }) {
  const [room, setRoom] = useState(
      new URLSearchParams(location.search).get("room") || "",
    ),
    [code, setCode] = useState(""),
    [err, setErr] = useState(""),
    [busy, setBusy] = useState(false);
  const local = localHost();
  const submit = async (create: boolean) => {
    setBusy(true);
    setErr("");
    try {
      onJoin(
        await api<Session>(
          create
            ? "/sessions"
            : "/sessions/" + encodeURIComponent(room.trim()) + "/join",
          json("POST", create ? {} : { code: code.trim() }),
        ),
      );
    } catch (e) {
      setErr(message(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="welcome">
      <div className="welcome-copy">
        <p className="eyebrow">
          LumiRead · {cameraRoute ? "虚拟眼镜" : "学习助手"}
        </p>
        <h1>{cameraRoute ? "连接你的学习助手" : "家长学习手册"}</h1>
        <p>
          {cameraRoute
            ? "用 iPhone 扫描家长端的配对二维码，或输入场次与配对码。"
            : "开启一次学习记录，即可在这里查看孩子刚拍下的作业与逐题讲解。"}
        </p>
        {!cameraRoute &&
          local &&
          !new URLSearchParams(location.search).get("room") && (
            <button disabled={busy} onClick={() => submit(true)}>
              创建学习场次
            </button>
          )}
      </div>
      <form
        className="paper"
        onSubmit={(e) => {
          e.preventDefault();
          void submit(false);
        }}
      >
        <h2>加入已有场次</h2>
        <label>
          场次编号
          <input
            required
            value={room}
            onChange={(e) => setRoom(e.target.value)}
            autoCapitalize="none"
          />
        </label>
        <label>
          一次性配对码
          <input
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoCapitalize="none"
          />
        </label>
        <button disabled={busy} className="outline">
          配对设备
        </button>
      </form>
      {err && (
        <p className="error" role="alert">
          {err}
        </p>
      )}
    </main>
  );
}
function Desk({ session }: { session: Session }) {
  const sid = session.session_id;
  const [snap, setSnap] = useState<Snapshot>(),
    [conn, setConn] = useState("连接中"),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  const [bus] = useState(() => new EventTarget());
  useEffect(() => {
    let active = true,
      cleanup = () => {};
    const abort = new AbortController();
    api<Snapshot>("/sessions/" + sid + "/snapshot", { signal: abort.signal })
      .then((s) => {
        if (!active) return;
        setError("");
        setSnap(s);
        cleanup = listen(
          sid,
          s.seq,
          (ev) => {
            if (ev.type === "session.privacy")
              setSnap(
                (current) =>
                  current && { ...current, silent: !!ev.payload.silent },
              );
            bus.dispatchEvent(new CustomEvent(ev.type, { detail: ev }));
            if (session.role === "glasses")
              window.dispatchEvent(
                new CustomEvent("lumiread:event", { detail: ev }),
              );
          },
          setConn,
        );
      })
      .catch((e) => {
        if (active) setError(message(e));
      });
    return () => {
      active = false;
      abort.abort();
      cleanup();
    };
  }, [session.role, sid, bus, retry]);
  if (!snap)
    return (
      <main>
        {error ? (
          <p className="error" role="alert">
            {error}{" "}
            <button onClick={() => setRetry((v) => v + 1)}>重新读取场次</button>
          </p>
        ) : (
          <p>正在读取设备状态…</p>
        )}
      </main>
    );
  if (session.role === "parent")
    return (
      <Suspense fallback={<main>正在打开手册…</main>}>
        <Notebook
          snap={snap}
          bus={bus}
          connection={conn}
          onSilent={(v) => setSnap((s) => s && { ...s, silent: v })}
        />
      </Suspense>
    );
  return (
    <main>
      <div className="subhead">
        <span>虚拟眼镜</span>
        <span className="connection">{conn}</span>
      </div>
      <Suspense fallback={<p>正在准备取景…</p>}>
        <Camera sid={sid} silent={snap.silent} />
      </Suspense>
    </main>
  );
}
function App() {
  const [session, setSession] = useState<Session | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  useEffect(() => {
    document.title = cameraRoute
      ? "LumiRead · 虚拟眼镜"
      : "LumiRead · 学习观察手册";
    const params = new URLSearchParams(location.hash.slice(1));
    const sid = params.get("room"),
      code = params.get("code");
    const action =
      sid && code
        ? api<Session>(
            "/sessions/" + encodeURIComponent(sid) + "/join",
            json("POST", { code }),
          )
        : api<Session>("/me");
    action
      .then((s) => {
        const requested = new URLSearchParams(location.search).get("room");
        if (requested && s.session_id !== requested) return;
        if ((cameraRoute ? "glasses" : "parent") === s.role) setSession(s);
        if (sid && code) history.replaceState(null, "", location.pathname);
      })
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 401)) setError(message(e));
      })
      .finally(() => setLoading(false));
  }, []);
  return (
    <>
      <nav className="mast">
        <Brand />
        <div className="mast-links">
          {!cameraRoute && (
            <a
              href={
                "/showcase" +
                (session
                  ? "?legacy=1&room=" + encodeURIComponent(session.session_id)
                  : "")
              }
            >
              产品展示 <span aria-hidden="true">↗</span>
            </a>
          )}
          <span>{cameraRoute ? "眼镜端" : "家庭端"}</span>
        </div>
      </nav>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {loading ? (
        <main>正在打开 LumiRead…</main>
      ) : session ? (
        <Desk session={session} />
      ) : (
        <Pair onJoin={setSession} />
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  cameraRoute || location.pathname === "/legacy-app" ? (
    <App />
  ) : (
    <Suspense fallback={<main>正在打开 LumiRead…</main>}>
      {location.pathname === "/app" ? (
        <Demo />
      ) : location.pathname === "/federated" ? (
        <Federated />
      ) : (
        <Showcase />
      )}
    </Suspense>
  ),
);
