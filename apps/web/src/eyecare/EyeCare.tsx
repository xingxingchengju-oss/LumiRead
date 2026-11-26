import { lazy, Suspense, useEffect, useState } from "react";
import "./eyecare.css";
const Reading = lazy(() => import("./Reading"));
const Reports = lazy(() => import("./Reports"));
const pages = {
  reading: "阅读监测",
  reports: "家长报告",
};
type Page = keyof typeof pages;
function section(): Page {
  const k = location.hash.slice(1);
  return Object.hasOwn(pages, k) ? (k as Page) : "reading";
}
export default function EyeCare() {
  const [page, choose] = useState<Page>(section);
  useEffect(() => {
    document.title = "LumiRead · 家庭护眼手册";
    const handle = () => {
      if (location.hash === "#timer" || location.hash === "#sensors")
        history.replaceState(
          history.state,
          "",
          location.pathname + location.search + "#reading",
        );
      choose(section());
    };
    handle();
    window.addEventListener("hashchange", handle);
    return () => window.removeEventListener("hashchange", handle);
  }, []);
  return (
    <div className="ec-shell">
      <header className="ec-mast">
        <a className="ec-brand" href="/">
          LumiRead
        </a>
        <nav aria-label="更多功能">
          <a href="/showcase">眼镜设计</a>
          <a href="/app">作业与学习</a>
          <a href="/federated">联邦实验</a>
        </nav>
      </header>
      <main>
        {page === "reading" && (
          <header className="ec-cover ec-cover-compact">
            <h1>家庭护眼手册</h1>
          </header>
        )}
        <nav className="ec-nav" aria-label="护眼手册目录">
          {(Object.keys(pages) as Page[]).map((k) => (
            <a
              key={k}
              href={"#" + k}
              aria-current={page === k ? "page" : undefined}
            >
              {pages[k]}
            </a>
          ))}
        </nav>
        <Suspense fallback={<p role="status">正在打开护眼记录…</p>}>
          {page === "reading" ? <Reading /> : <Reports />}
        </Suspense>
      </main>
    </div>
  );
}
