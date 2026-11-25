import { lazy, Suspense, useEffect, useState } from "react";
import "./eyecare.css";
const Reading = lazy(() => import("./Reading"));
const Sensors = lazy(() => import("./Sensors"));
const Timer = lazy(() => import("./Timer"));
const Reports = lazy(() => import("./Reports"));
const pages = {
  reading: "阅读识别",
  sensors: "距离与光照",
  timer: "读写与休息",
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
    const handle = () => choose(section());
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
        <header className="ec-cover">
          <div>
            <h1>家庭护眼手册</h1>
            <p>观察阅读片段，回看距离与光线提醒，了解每一天的用眼记录。</p>
          </div>
          <img
            src="/products/frame-open.webp"
            alt="LumiRead 智能眼镜概念设计"
          />
        </header>
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
          {page === "reading" ? (
            <Reading />
          ) : page === "sensors" ? (
            <Sensors />
          ) : page === "timer" ? (
            <Timer />
          ) : (
            <Reports />
          )}
        </Suspense>
      </main>
    </div>
  );
}
