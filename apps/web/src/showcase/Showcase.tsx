import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from "react";
import { api, message, type Catalog } from "../api";
import {
  chapters,
  choices,
  explanation,
  exposedTemple,
  markers,
  partGroups,
  parts,
  type Chapter,
  type Part,
  type Selection,
  type Wear,
} from "./product";
import "./showcase.css";

const Viewer = lazy(() => import("./Viewer"));
const money = (value: number) => "¥" + value.toLocaleString("zh-CN");

function useChapter() {
  const [chapter, setChapter] = useState<Chapter>("top");
  useLayoutEffect(() => {
    const stops = chapters.map(({ id }) => document.getElementById(id)!);
    let ticket = 0;
    const measure = () => {
      ticket = 0;
      const threshold = window.innerHeight * 0.5;
      let current: Chapter = "top";
      for (const [index, el] of stops.entries()) {
        if (el.getBoundingClientRect().top <= threshold)
          current = chapters[index].id;
      }
      setChapter(current);
    };
    const schedule = () => {
      if (!ticket) ticket = requestAnimationFrame(measure);
    };
    const initial = stops.find((el) => "#" + el.id === location.hash);
    if (initial) initial.scrollIntoView({ behavior: "instant" });
    measure();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      cancelAnimationFrame(ticket);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, []);
  return chapter;
}

function LensOptions({
  wear,
  choose,
}: {
  wear: Wear;
  choose: (mode: Wear) => void;
}) {
  return (
    <div className="lr-options" role="group" aria-label="选择佩戴方式">
      {choices.map((choice) => (
        <button
          key={choice.id}
          type="button"
          className="lr-choice"
          aria-pressed={wear === choice.id}
          onClick={() => choose(choice.id)}
        >
          <span className={"lr-swatch is-" + choice.id} aria-hidden="true" />
          <span>{choice.label}</span>
          <i aria-hidden="true" />
        </button>
      ))}
      <p className="lr-option-note" aria-live="polite">
        {choices.find((choice) => choice.id === wear)!.detail}
      </p>
    </div>
  );
}

function PartLinks({
  items,
  pick,
}: {
  items: Part[];
  pick: (item: Selection) => void;
}) {
  return (
    <div className="lr-part-links">
      {items.map((id) => (
        <button key={id} type="button" onClick={() => pick({ part: id })}>
          {parts[id].name}
          <span aria-hidden="true">+</span>
        </button>
      ))}
    </div>
  );
}

function BookMark() {
  return (
    <span className="lr-book" aria-hidden="true">
      <i />
      <i />
    </span>
  );
}

type PosterPoints = Record<string, Record<string, [number, number]>>;
function Poster({
  wear,
  chapter,
  selected,
  interactive,
  select,
}: {
  wear: Wear;
  chapter: Chapter;
  selected: Selection | null;
  interactive: boolean;
  select: (item: Selection) => void;
}) {
  const [points, setPoints] = useState<PosterPoints>();
  useEffect(() => {
    if (!interactive) return;
    const controller = new AbortController();
    fetch("/products/poster-points.json", { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : undefined))
      .then(setPoints)
      .catch(() => {});
    return () => controller.abort();
  }, [interactive]);
  const clip = wear === "clip";
  const key = clip
    ? "clip"
    : exposedTemple(selected?.part)
      ? "frame-inside"
      : wear === "open"
        ? "frame-open"
        : "frame";
  const positions = points?.[key];
  const focus =
    selected && selected.part !== "lens" && positions?.[selected.part];
  const framing = focus
    ? {
        transform:
          "scale(2.35) translate(" +
          (50 - focus[0] * 100) +
          "%, " +
          (50 - focus[1] * 100) +
          "%)",
      }
    : undefined;
  return (
    <div className="lr-poster">
      <div className="lr-poster-art" style={framing}>
        <img
          src={"/products/" + key + ".webp"}
          alt={
            {
              clip: "智能夹片装在普通眼镜上",
              "frame-inside": "镜腿外壳透视，可见右侧主板和左侧电池",
              "frame-open": "无镜片一体镜",
              frame: "LumiRead 烟灰色智能学习眼镜",
            }[key]
          }
          fetchPriority="high"
        />
        {interactive && positions && (
          <>
            {["lens", "lens-other"].map(
              (id) =>
                positions[id] && (
                  <button
                    key={id}
                    type="button"
                    className="lr-empty-hit"
                    aria-label="在镜圈处选择佩戴方式"
                    style={{
                      left: positions[id][0] * 100 + "%",
                      top: positions[id][1] * 100 + "%",
                    }}
                    onClick={() => select({ part: "lens" })}
                  />
                ),
            )}
            {markers(chapter, clip, !!selected).map(
              (id) =>
                positions[id] && (
                  <button
                    className="lr-pin"
                    key={id}
                    aria-label={parts[id].name + "热点"}
                    style={{
                      left: positions[id][0] * 100 + "%",
                      top: positions[id][1] * 100 + "%",
                    }}
                    onClick={() => select({ part: id })}
                  >
                    <span aria-hidden="true">+</span>
                  </button>
                ),
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function Showcase() {
  const chapter = useChapter();
  const [wear, setWear] = useState<Wear>("blue");
  const [selected, setSelected] = useState<Selection | null>(null);
  const [catalog, setCatalog] = useState<Catalog>();
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [paused, setPaused] = useState(false);
  const [hidden, setHidden] = useState(document.hidden);
  const [reduced, setReduced] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [indexOpen, setIndexOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const picker = useRef<HTMLButtonElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const clip = wear === "clip";
  const group = partGroups(clip);
  const focusedPart = selected?.part;
  const hero = chapter === "top" && !selected;
  const optical =
    focusedPart === "lens" || (!selected && chapter === "explore");
  const light = optical || (!selected && chapter === "specifications");
  const activeChapter = chapters.find((s) => s.id === chapter)!;
  const sceneReady = useCallback(() => setReady(true), []);
  const sceneFailed = useCallback(() => setFailed(true), []);
  const pause = useCallback(() => setPaused(true), []);
  const rotate = !paused && !hidden && !reduced && !selected && !indexOpen;

  useEffect(() => {
    document.title = "LumiRead · 智能学习眼镜";
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const motion = () => setReduced(media.matches);
    const visibility = () => setHidden(document.hidden);
    media.addEventListener("change", motion);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      media.removeEventListener("change", motion);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    api<Catalog>("/products", { signal: controller.signal })
      .then(setCatalog)
      .catch((e) => {
        if (!controller.signal.aborted) setError(message(e));
      });
    return () => controller.abort();
  }, [attempt]);
  useEffect(() => {
    if (selected) detailHeading.current?.focus({ preventScroll: true });
  }, [selected]);

  const select = useCallback(
    (item: Selection) => {
      if (!selected)
        previousFocus.current =
          document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null;
      dialog.current?.close();
      setSelected(item);
    },
    [selected],
  );
  const back = useCallback(() => {
    setSelected(null);
    const old = previousFocus.current;
    requestAnimationFrame(() => {
      (old?.isConnected && old !== document.body && !old.closest("dialog")
        ? old
        : picker.current
      )?.focus({ preventScroll: true });
    });
  }, []);
  useEffect(() => {
    const escape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && selected && !dialog.current?.open) back();
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [selected, back]);
  const go = (event: MouseEvent<HTMLAnchorElement>, id: Chapter) => {
    if (
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      event.button !== 0
    )
      return;
    event.preventDefault();
    setSelected(null);
    if (location.hash !== "#" + id) history.pushState(null, "", "#" + id);
    document.getElementById(id)?.scrollIntoView({ behavior: "instant" });
  };
  const onIndexKey = (event: KeyboardEvent<HTMLDialogElement>) => {
    if (event.key === "Escape") event.stopPropagation();
  };
  const params = new URLSearchParams(location.search);
  const room = params.get("legacy") === "1" ? params.get("room") : null;
  const assistant = room
    ? "/legacy-app?room=" + encodeURIComponent(room)
    : catalog?.assistant_path || "/app";
  const frameProduct = catalog?.products.find((p) => p.sku === "frame");
  const clipProduct = catalog?.products.find((p) => p.sku === "clip");
  const next = chapters[chapters.findIndex((c) => c.id === chapter) + 1];
  const heading = optical
    ? "三种佩戴方式"
    : focusedPart
      ? parts[focusedPart].name
      : "";
  const showPoster = failed || !ready;

  return (
    <div className="lr-show" data-light={light}>
      <nav className="lr-nav" aria-label="产品导航">
        <div className="lr-nav-inner">
          <a
            className="lr-brand"
            href="#top"
            aria-label="LumiRead 产品首页"
            onClick={(e) => go(e, "top")}
          >
            <BookMark />
            <b>LumiRead</b>
          </a>
          <div className="lr-nav-links">
            {chapters.map((s) => (
              <a
                key={s.id}
                href={"#" + s.id}
                aria-current={chapter === s.id ? "location" : undefined}
                className={
                  s.id === "specifications" ? "lr-price-link" : undefined
                }
                onClick={(e) => go(e, s.id)}
              >
                {s.id === "specifications" ? "查看价格" : s.label}
              </a>
            ))}
          </div>
        </div>
      </nav>
      <main className="lr-main" aria-label="LumiRead 产品展示">
        <div
          className="lr-stage"
          data-hero={hero}
          data-light={light}
          data-focus={!!selected}
          data-chapter={chapter}
          data-wear={wear}
        >
          <div className="lr-lightwash" aria-hidden="true" />
          <div className="lr-stage-inner">
            <header className="lr-hero-title" hidden={!hero}>
              <h1>
                <span className="lr-wordmark">LumiRead</span>
                <span className="lr-hero-name">智能学习眼镜</span>
              </h1>
            </header>
            <div
              className="lr-surface"
              role="region"
              aria-label="交互眼镜模型"
              aria-description={
                failed
                  ? undefined
                  : "可拖动或用方向键旋转眼镜，点击部件查看特写。"
              }
              tabIndex={failed ? undefined : 0}
              aria-keyshortcuts="ArrowLeft ArrowRight ArrowUp ArrowDown"
              data-renderer={failed ? "poster" : ready ? "webgl" : "loading"}
            >
              {showPoster && (
                <Poster
                  wear={wear}
                  chapter={chapter}
                  selected={selected}
                  interactive={failed}
                  select={select}
                />
              )}
              {!failed && (
                <Suspense fallback={null}>
                  <Viewer
                    frameUrl={frameProduct?.model_url || "/products/frame.glb"}
                    clipUrl={clipProduct?.model_url || "/products/clip.glb"}
                    wear={wear}
                    chapter={selected ? "top" : chapter}
                    selected={selected}
                    rotate={rotate}
                    reduced={reduced}
                    sleep={hidden}
                    select={select}
                    pause={pause}
                    ready={sceneReady}
                    fail={sceneFailed}
                  />
                </Suspense>
              )}
            </div>
            {hero ? (
              <button
                type="button"
                className="lr-lens-prompt"
                onClick={() => select({ part: "lens" })}
              >
                <span className="lr-prompt-plus" aria-hidden="true">
                  +
                </span>
                点镜片，试试三种戴法
              </button>
            ) : (
              <section
                className="lr-copy"
                key={focusedPart || chapter}
                aria-label={heading || activeChapter.label}
              >
                {selected && (
                  <button type="button" className="lr-back" onClick={back}>
                    <span aria-hidden="true">×</span> 返回全貌
                  </button>
                )}
                {optical ? (
                  <>
                    <h2 ref={detailHeading} tabIndex={-1}>
                      三种佩戴方式
                    </h2>
                    <LensOptions wear={wear} choose={setWear} />
                  </>
                ) : focusedPart ? (
                  <>
                    <p className="lr-kicker">
                      {clip ? "智能夹装模块" : "一体式全框眼镜"}
                    </p>
                    <h2 ref={detailHeading} tabIndex={-1}>
                      {parts[focusedPart].name}
                    </h2>
                    <p className="lr-description">
                      {explanation(focusedPart, clip)}
                    </p>
                    {exposedTemple(focusedPart) && (
                      <PartLinks
                        items={
                          focusedPart === "board"
                            ? ["battery"]
                            : focusedPart === "battery"
                              ? ["board"]
                              : ["board", "battery"]
                        }
                        pick={select}
                      />
                    )}
                    {focusedPart === "clamp" && (
                      <PartLinks items={["pad", "button"]} pick={select} />
                    )}
                  </>
                ) : chapter === "sensing" ? (
                  <>
                    <p className="lr-kicker">学习感知</p>
                    <h2>
                      眼镜如何感知
                      <br />
                      读写环境
                    </h2>
                    <p className="lr-description">
                      {clip
                        ? "摄像头、测距和测光窗口，都在银色模块正面。"
                        : "两侧看纸面与光线，鼻梁中央测量阅读距离。"}
                    </p>
                    <PartLinks
                      items={["camera", "tof", "light"]}
                      pick={select}
                    />
                  </>
                ) : chapter === "construction" ? (
                  <>
                    <p className="lr-kicker">佩戴结构</p>
                    <h2>
                      {clip ? (
                        <>
                          夹扣如何固定
                          <br />
                          在镜框上
                        </>
                      ) : (
                        <>
                          镜腿里的
                          <br />
                          主板与电池
                        </>
                      )}
                    </h2>
                    <p className="lr-description">
                      {clip
                        ? "弹簧提供夹持力，内侧硅胶垫贴住自己的镜框。"
                        : "点一侧镜腿，看外壳下的电路与供电结构。"}
                    </p>
                    <PartLinks
                      items={
                        clip
                          ? ["clamp", "pad", "button"]
                          : ["temple-right", "temple-left"]
                      }
                      pick={select}
                    />
                    {clip ? (
                      <p className="lr-spec-note">
                        夹装模块目标重量约 {clipProduct?.weight_g ?? 13} g
                      </p>
                    ) : (
                      <dl className="lr-dimensions">
                        {[
                          ["129", "镜框宽"],
                          ["41", "镜框高"],
                          ["136", "镜腿长"],
                        ].map(([n, label]) => (
                          <div key={label}>
                            <dt>{label}</dt>
                            <dd>约 {n} mm</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </>
                ) : (
                  <>
                    <p className="lr-kicker">概念拟定价</p>
                    <h2>型号与价格</h2>
                    {catalog && frameProduct && clipProduct ? (
                      <dl className="lr-prices">
                        <div>
                          <dt>一体镜</dt>
                          <dd>{money(frameProduct.price_cny)}</dd>
                        </div>
                        <div>
                          <dt>智能夹片</dt>
                          <dd>{money(clipProduct.price_cny)}</dd>
                        </div>
                        <div>
                          <dt>家庭学习服务</dt>
                          <dd>
                            {money(catalog.subscription_cny)}
                            <small> / 年</small>
                          </dd>
                        </div>
                      </dl>
                    ) : (
                      <div className="lr-catalog-state">
                        <p role={error ? "alert" : "status"}>
                          {error ||
                            (catalog
                              ? "产品目录暂无型号。"
                              : "正在读取产品目录…")}
                        </p>
                        {error && (
                          <button onClick={() => setAttempt((n) => n + 1)}>
                            重新读取产品
                          </button>
                        )}
                      </div>
                    )}
                    <a className="lr-assistant" href={assistant}>
                      进入学习助手
                    </a>
                  </>
                )}
              </section>
            )}
            <div className="lr-stage-foot">
              {next ? (
                <a
                  className="lr-scroll-link"
                  href={"#" + next.id}
                  onClick={(e) => go(e, next.id)}
                >
                  <i className="lr-scroll-symbol" aria-hidden="true" />{" "}
                  <span>{chapter === "top" ? "向下探索" : next.label}</span>
                </a>
              ) : (
                <a
                  className="lr-scroll-link"
                  href="#top"
                  onClick={(e) => go(e, "top")}
                >
                  回到概览
                </a>
              )}
              <div className="lr-tools">
                {failed ? (
                  <span className="lr-fallback-note">产品渲染图</span>
                ) : (
                  ready &&
                  !selected &&
                  !reduced && (
                    <button
                      type="button"
                      className="lr-rotate"
                      onClick={() => setPaused((old) => !old)}
                      aria-pressed={!paused}
                      aria-label={paused ? "继续旋转" : "暂停旋转"}
                      title={paused ? "继续旋转" : "暂停旋转"}
                    >
                      <i
                        aria-hidden="true"
                        className={paused ? "lr-play" : "lr-pause"}
                      />
                    </button>
                  )
                )}
                <button
                  ref={picker}
                  type="button"
                  className="lr-index-button"
                  aria-haspopup="dialog"
                  onClick={() => {
                    dialog.current?.showModal();
                    setIndexOpen(true);
                  }}
                >
                  <i className="lr-index-icon" aria-hidden="true" />
                  部件目录
                </button>
              </div>
            </div>
          </div>
        </div>
        <div className="lr-track" aria-hidden="true">
          {chapters.map(({ id }) => (
            <div key={id} id={id} />
          ))}
        </div>
      </main>
      <dialog
        ref={dialog}
        className="lr-index"
        aria-labelledby="lr-index-title"
        onKeyDown={onIndexKey}
        onClose={() => setIndexOpen(false)}
        onClick={(e) => {
          if (e.target === dialog.current) dialog.current?.close();
        }}
      >
        <div className="lr-index-inside">
          <div className="lr-index-head">
            <h2 id="lr-index-title">部件目录</h2>
            <button
              type="button"
              aria-label="关闭部件目录"
              onClick={() => dialog.current?.close()}
            >
              ×
            </button>
          </div>
          {group.map((g) => (
            <div className="lr-index-group" key={g.title}>
              <h3>{g.title}</h3>
              <PartLinks items={g.items} pick={select} />
            </div>
          ))}
        </div>
      </dialog>
    </div>
  );
}
