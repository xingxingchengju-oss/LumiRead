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
  type RefObject,
} from "react";
import { api, message, type Catalog } from "../api";
import {
  chapters,
  choices,
  explanation,
  exposedShell,
  posterKey,
  wholePosters,
  sensors,
  type PosterPoints,
  markers,
  partGroups,
  parts,
  type Chapter,
  type Part,
  type Selection,
  type Wear,
} from "./product";
import { SensingPaper, RangeLine } from "./Sensing";
import StructureGuide from "./StructureGuide";
import { clipSteps, frameSteps } from "./structure";
import { useShowcaseScroll } from "./useShowcaseScroll";
import "./showcase.css";

const Viewer = lazy(() => import("./Viewer"));
const money = (value: number) => "¥" + value.toLocaleString("zh-CN");

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
  pick: (item: Selection, trigger?: HTMLElement) => void;
}) {
  return (
    <div className="lr-part-links">
      {items.map((id) => (
        <button
          key={id}
          type="button"
          data-return={"link-" + id}
          onClick={(e) => pick({ part: id }, e.currentTarget)}
        >
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

function ProductNav({
  chapter,
  go,
}: {
  chapter: Chapter;
  go: (event: MouseEvent<HTMLAnchorElement>, id: Chapter) => void;
}) {
  const [open, setOpen] = useState(false);
  const nav = useRef<HTMLElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const label = chapters.find((c) => c.id === chapter)!.label;
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      if (!nav.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  const navigate = (e: MouseEvent<HTMLAnchorElement>, id: Chapter) => {
    if (open && e.detail === 0) toggle.current?.focus();
    setOpen(false);
    go(e, id);
  };
  return (
    <nav
      ref={nav}
      className="lr-nav"
      aria-label="产品导航"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(e) => {
        if (open && e.key === "Escape") {
          e.stopPropagation();
          setOpen(false);
          toggle.current?.focus();
        }
      }}
    >
      <div className="lr-nav-inner">
        <a
          className="lr-brand"
          href="#top"
          aria-label="LumiRead 产品首页"
          onClick={(e) => navigate(e, "top")}
        >
          <BookMark />
          <b>LumiRead</b>
        </a>
        <div className="lr-nav-links">
          <button
            type="button"
            ref={toggle}
            className="lr-chapter-toggle"
            aria-expanded={open}
            aria-controls="lr-chapter-list"
            aria-label={"浏览章节，当前为" + label}
            onClick={() => setOpen(!open)}
          >
            {label}
          </button>
          <div
            id="lr-chapter-list"
            className="lr-chapter-list"
            data-open={open}
          >
            <a href="/">护眼手册</a>
            {chapters
              .filter((c) => c.id !== "specifications")
              .map((c) => (
                <a
                  key={c.id}
                  href={"#" + c.id}
                  aria-current={chapter === c.id ? "location" : undefined}
                  onClick={(e) => navigate(e, c.id)}
                >
                  {c.label}
                </a>
              ))}
          </div>
          <a
            href="#specifications"
            className="lr-price-link"
            aria-current={chapter === "specifications" ? "location" : undefined}
            onClick={(e) => navigate(e, "specifications")}
          >
            查看价格
          </a>
        </div>
      </div>
    </nav>
  );
}

function Poster({
  wear,
  chapter,
  selected,
  interactive,
  photographing,
  project,
  points,
  select,
}: {
  wear: Wear;
  chapter: Chapter;
  selected: Selection | null;
  interactive: boolean;
  photographing: boolean;
  project: RefObject<(() => void) | null>;
  points?: PosterPoints;
  select: (item: Selection, trigger?: HTMLElement) => void;
}) {
  const [painted, setPainted] = useState<{
    src: string;
    srcSet?: string;
    sizes: string;
    alt: string;
  }>();
  const art = useRef<HTMLDivElement>(null);
  const key = posterKey(wear, selected),
    whole = wholePosters.has(key);
  const clip = wear === "clip",
    positions = points?.[key],
    src = "/products/" + key;
  useLayoutEffect(() => {
    if (!art.current || !interactive) return;
    const update = () => project.current?.();
    const observer = new ResizeObserver(update);
    observer.observe(art.current);
    update();
    return () => observer.disconnect();
  }, [key, painted?.src, points, project, interactive]);
  const place = (id: string) => ({
    left: positions![id][0] * 100 + "%",
    top: positions![id][1] * 100 + "%",
  });
  const alt =
    selected && selected.part !== "lens"
      ? parts[selected.part].name + "的产品设计特写"
      : clip
        ? "智能夹片装在普通镜框上"
        : wear === "open"
          ? "无镜片一体镜"
          : "LumiRead 烟灰色智能学习眼镜";
  const requested = {
    src: src + ".webp",
    srcSet:
      whole && interactive
        ? src + ".webp 1440w, " + src + "@2x.webp 2880w"
        : undefined,
    sizes:
      selected || chapter !== "top" ? "(max-width: 700px) 96vw, 60vw" : "100vw",
    alt,
  };
  const waiting = painted && painted.src !== requested.src;
  const images = waiting ? [painted, requested] : [requested];
  return (
    <div className="lr-poster" data-macro={!whole}>
      <div className="lr-poster-art" ref={art}>
        {images.map((image) => (
          <img
            key={image.src}
            {...image}
            hidden={waiting && image === requested}
            fetchPriority="high"
            onLoad={() => {
              if (image === requested) {
                setPainted(requested);
              }
            }}
          />
        ))}
        {interactive && painted?.src === requested.src && positions && (
          <>
            {(!selected || selected.part === "lens") &&
              ["lens", "lens-other"].map(
                (id) =>
                  positions[id] && (
                    <button
                      key={id}
                      type="button"
                      className="lr-empty-hit"
                      data-return={"optic-" + id}
                      aria-label="在镜圈处选择佩戴方式"
                      style={place(id)}
                      onClick={(e) => select({ part: "lens" }, e.currentTarget)}
                    />
                  ),
              )}
            {markers(chapter, clip, !!selected).map(
              (id) =>
                positions[id] && (
                  <button
                    key={id}
                    type="button"
                    className="lr-pin"
                    data-return={"pin-" + id}
                    aria-label={parts[id].name + "热点"}
                    style={place(id)}
                    onClick={(e) => select({ part: id }, e.currentTarget)}
                  >
                    <span aria-hidden="true">+</span>
                  </button>
                ),
            )}
            {selected?.part === "tof" && positions.tof && (
              <i
                className="lr-range-origin"
                style={place("tof")}
                aria-hidden="true"
              />
            )}
            {photographing && positions.led && (
              <i
                className="lr-poster-led"
                style={place("led")}
                aria-hidden="true"
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function Showcase() {
  const { chapter, step, reveal, track, guidePosition, restoreGuide } =
    useShowcaseScroll();
  const [points, setPoints] = useState<PosterPoints>();
  useEffect(() => {
    const control = new AbortController();
    fetch("/products/poster-points.json", { signal: control.signal })
      .then((r) => (r.ok ? r.json() : undefined))
      .then(setPoints)
      .catch(() => {});
    return () => control.abort();
  }, []);
  const project = useRef<(() => void) | null>(null);
  const [wear, setWear] = useState<Wear>("blue");
  const [selected, setSelected] = useState<Selection | null>(null);
  const [catalog, setCatalog] = useState<Catalog>();
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [renderedUrl, setRenderedUrl] = useState("");
  const surface = useRef<HTMLDivElement>(null);
  const [flash, setFlash] = useState(false);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const capture = useCallback(() => {
    clearTimeout(flashTimer.current);
    setFlash(true);
    flashTimer.current = setTimeout(() => setFlash(false), 850);
  }, []);
  useEffect(() => () => clearTimeout(flashTimer.current), []);
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
  const guideBookmark = useRef<number | null>(null);
  const returnOnClose = useRef(false);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const clip = wear === "clip";
  const group = partGroups(clip);
  const focusedPart = selected?.part;
  const hero = chapter === "top" && !selected;
  const guided = chapter === "construction" && !selected;
  const optical =
    focusedPart === "lens" || (!selected && chapter === "explore");
  const light = optical || (!selected && chapter === "specifications");
  const activeChapter = chapters.find((s) => s.id === chapter)!;
  const sceneReady = useCallback((url: string) => setRenderedUrl(url), []);
  const sceneFailed = useCallback(() => setFailed(true), []);
  const pause = useCallback(() => setPaused(true), []);
  const rotate =
    !paused && !hidden && !reduced && !selected && !indexOpen && !guided;

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
    (item: Selection, trigger?: HTMLElement) => {
      if (!selected) {
        guideBookmark.current = guidePosition.current;
        previousFocus.current =
          trigger ??
          (document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null);
      }
      dialog.current?.close();
      setSelected(item);
      if (item.part === "camera") capture();
    },
    [selected, capture, guidePosition],
  );
  const back = useCallback(() => {
    if (guideBookmark.current !== null) {
      restoreGuide(guideBookmark.current);
      guideBookmark.current = null;
    }
    returnOnClose.current = true;
    setSelected(null);
  }, [restoreGuide]);
  useLayoutEffect(() => {
    if (selected || !returnOnClose.current) return;
    returnOnClose.current = false;
    const old = previousFocus.current;
    const fallback = picker.current;
    const stage = fallback?.closest(".lr-stage");
    if (!fallback || !stage) return;
    const key = old?.dataset.return;
    const selector = key && '[data-return="' + CSS.escape(key) + '"]';
    const restore = () => {
      const target =
        old?.isConnected && old !== document.body
          ? old
          : selector
            ? stage.querySelector<HTMLElement>(selector)
            : null;
      if (!target || target.hidden) return false;
      target.focus({ preventScroll: true });
      return document.activeElement === target;
    };
    if (!old?.closest("dialog") && restore()) return;
    fallback.focus({ preventScroll: true });
    const expectedPin = markers(chapter, clip, false).some(
      (id) => key === "pin-" + id,
    );
    if (!expectedPin && !key?.startsWith("optic-")) return;
    // The return flight or a decoded poster may make the originating control available later.
    const observer = new MutationObserver(() => {
      if (document.activeElement !== fallback || restore())
        observer.disconnect();
    });
    observer.observe(stage, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["hidden"],
    });
    const stop = () => observer.disconnect();
    fallback.addEventListener("blur", stop, { once: true });
    return () => {
      observer.disconnect();
      fallback.removeEventListener("blur", stop);
    };
  }, [selected, chapter, clip]);
  useEffect(() => {
    const escape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && selected && !dialog.current?.open) back();
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [selected, back]);
  const go = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    if (
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      event.button !== 0
    )
      return;
    event.preventDefault();
    guideBookmark.current = null;
    setSelected(null);
    if (location.hash !== "#" + id) history.pushState(null, "", "#" + id);
    document.getElementById(id)?.scrollIntoView({
      behavior:
        reduced || id === "specifications" || chapter === "specifications"
          ? "instant"
          : "smooth",
    });
  };
  const onIndexKey = (event: KeyboardEvent<HTMLDialogElement>) => {
    if (event.key === "Escape") event.stopPropagation();
  };
  const params = new URLSearchParams(location.search);
  const room = params.get("legacy") === "1" ? params.get("room") : null;
  const assistant = room
    ? "/legacy-app?room=" + encodeURIComponent(room)
    : catalog?.assistant_path || "/app";
  const assistantLink = (
    <a className="lr-assistant" href={assistant}>
      进入学习助手
    </a>
  );
  const frameProduct = catalog?.products.find((p) => p.sku === "frame");
  const clipProduct = catalog?.products.find((p) => p.sku === "clip");
  const steps = clip ? clipSteps : frameSteps;
  let next: { id: string; label: string } | undefined =
    chapters[chapters.findIndex((c) => c.id === chapter) + 1];
  if (guided) {
    if (steps[step].cover && !reveal)
      next = { id: `construction-${step + 1}-inside`, label: "查看内部" };
    else if (step + 1 < steps.length)
      next = { id: `construction-${step + 2}`, label: "下一幕" };
  }
  const heading = optical
    ? "三种佩戴方式"
    : focusedPart
      ? parts[focusedPart].name
      : "";
  const frameUrl = frameProduct?.model_url || "/products/frame.glb",
    clipUrl = clipProduct?.model_url || "/products/clip.glb";
  const ready = renderedUrl === (clip ? clipUrl : frameUrl);
  const showingModel = ready && !failed;
  const chooseWear = (next: Wear) => {
    if ((next === "clip") !== clip) setRenderedUrl("");
    setWear(next);
  };
  useLayoutEffect(() => {
    if (guided) surface.current?.setAttribute("aria-busy", "false");
    else if (!ready || failed)
      surface.current?.setAttribute("aria-busy", String(!failed));
  }, [ready, failed, guided]);
  const photographing = flash && focusedPart === "camera";

  return (
    <div className="lr-show" data-light={light}>
      <ProductNav chapter={chapter} go={go} />
      <main className="lr-main" aria-label="LumiRead 产品展示">
        <div
          className="lr-stage"
          data-hero={hero}
          data-light={light}
          data-focus={!!selected}
          data-chapter={chapter}
          data-wear={wear}
          data-guided={guided}
        >
          <div className="lr-lightwash" aria-hidden="true" />
          <div className="lr-stage-inner">
            <header className="lr-hero-title" hidden={!hero}>
              <h1>
                <span className="lr-wordmark">LumiRead</span>
                <span className="lr-hero-name">智能学习眼镜</span>
              </h1>
              <div className="lr-hero-intro">
                <p className="lr-concept">无屏眼镜概念设计</p>
                <p>
                  留意读写距离与光线，
                  <br />
                  拍下眼前的作业。
                </p>
              </div>
            </header>
            <div
              className="lr-surface"
              ref={surface}
              role="region"
              aria-label="交互眼镜模型"
              aria-description={
                guided
                  ? "向下滚动查看下一幕，向上滚动回看。"
                  : failed
                    ? undefined
                    : "可拖动或用方向键旋转眼镜，点击部件查看特写。"
              }
              tabIndex={failed && !guided ? undefined : 0}
              aria-keyshortcuts={
                guided ? undefined : "ArrowLeft ArrowRight ArrowUp ArrowDown"
              }
              data-renderer={failed ? "poster" : ready ? "webgl" : "loading"}
            >
              <div
                className="lr-model-layer"
                inert={guided}
                aria-hidden={guided}
              >
                <Poster
                  wear={wear}
                  chapter={showingModel || guided ? "top" : chapter}
                  selected={showingModel ? null : selected}
                  interactive={failed && !guided}
                  points={points}
                  photographing={photographing}
                  project={project}
                  select={select}
                />
                {!failed && (
                  <Suspense fallback={null}>
                    <Viewer
                      frameUrl={frameUrl}
                      clipUrl={clipUrl}
                      wear={wear}
                      chapter={chapter}
                      track={track}
                      project={project}
                      photographing={photographing}
                      selected={selected}
                      rotate={rotate}
                      reduced={reduced}
                      sleep={hidden || (guided && ready)}
                      select={select}
                      pause={pause}
                      ready={sceneReady}
                      fail={sceneFailed}
                    />
                  </Suspense>
                )}
              </div>
              <StructureGuide
                active={guided}
                warm={!selected && chapter === "explore"}
                wear={wear}
                index={step}
                reveal={reveal}
                reduced={reduced}
                points={points}
                weight={clipProduct?.weight_g ?? 13}
                select={select}
              />
            </div>
            {hero ? (
              <button
                type="button"
                className="lr-lens-prompt"
                data-return="wear-prompt"
                onClick={(e) => select({ part: "lens" }, e.currentTarget)}
              >
                <span className="lr-prompt-plus" aria-hidden="true">
                  +
                </span>
                点镜片，试试三种戴法
              </button>
            ) : guided ? null : (
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
                    <LensOptions wear={wear} choose={chooseWear} />
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
                    {sensors.includes(focusedPart) && (
                      <>
                        <SensingPaper
                          part={focusedPart}
                          photographing={photographing}
                          capture={capture}
                        />
                        {focusedPart === "camera" ? (
                          <a className="lr-inline-link" href={assistant}>
                            进入学习助手 <span aria-hidden="true">↗</span>
                          </a>
                        ) : (
                          <p className="lr-source-note">
                            学习助手中的距离与照度回放来自 Clouclip
                            成人佩戴记录。
                          </p>
                        )}
                      </>
                    )}
                    {(focusedPart === "eye" || focusedPart === "imu") && (
                      <>
                        <a className="lr-inline-link" href="/#reading">
                          观看研究样片 <span aria-hidden="true">↗</span>
                        </a>
                        <p className="lr-source-note">
                          当前演示使用 Meta RitW
                          成人研究录像。样机的识别表现仍待验证。
                        </p>
                      </>
                    )}
                    {!clip && exposedShell(focusedPart, false) && (
                      <PartLinks
                        items={
                          focusedPart === "board"
                            ? ["imu", "radio", "battery"]
                            : focusedPart === "battery"
                              ? ["charge", "board"]
                              : focusedPart === "temple-left"
                                ? ["battery", "charge"]
                                : ["board", "imu", "battery"]
                        }
                        pick={select}
                      />
                    )}
                    {clip &&
                      (focusedPart === "clamp" ||
                        focusedPart === "clip-core") && (
                        <PartLinks
                          items={
                            focusedPart === "clamp"
                              ? ["clip-core", "button"]
                              : ["radio", "charge", "clamp"]
                          }
                          pick={select}
                        />
                      )}
                  </>
                ) : chapter === "sensing" ? (
                  <>
                    <p className="lr-kicker">学习感知</p>
                    <h2>眼前的一页作业</h2>
                    <p className="lr-description">
                      点选窗口，看眼镜怎样测距、感知明暗，或拍下这道题。
                    </p>
                    <SensingPaper photographing={false} capture={capture} />
                    <PartLinks items={sensors} pick={select} />
                  </>
                ) : (
                  <>
                    <p className="lr-kicker">概念拟定价</p>
                    <h2>型号与价格</h2>
                    {catalog && frameProduct && clipProduct ? (
                      <>
                        <table
                          className="lr-compare"
                          aria-label="两款眼镜功能对照"
                        >
                          <thead>
                            <tr>
                              <th scope="col">规格</th>
                              <th scope="col">一体镜</th>
                              <th scope="col">智能夹片</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr>
                              <th scope="row">拟定价</th>
                              <td>{money(frameProduct.price_cny)}</td>
                              <td>{money(clipProduct.price_cny)}</td>
                            </tr>
                            <tr>
                              <th scope="row">读写感知</th>
                              <td colSpan={2}>测距、测光、拍作业</td>
                            </tr>
                            <tr>
                              <th scope="row">拍摄操作</th>
                              <td>双击镜腿</td>
                              <td>按顶部按键</td>
                            </tr>
                            <tr>
                              <th scope="row">阅读识别设计</th>
                              <td>眼动与头动</td>
                              <td aria-label="夹片未配置眼动模组">—</td>
                            </tr>
                            <tr>
                              <th scope="row">佩戴方式</th>
                              <td>无镜片或平光</td>
                              <td>保留原有镜片</td>
                            </tr>
                          </tbody>
                        </table>
                        <div className="lr-service">
                          <div className="lr-family-price">
                            <span>家庭学习服务</span>
                            <b>
                              {money(catalog.subscription_cny)}{" "}
                              <small>/ 年</small>
                            </b>
                          </div>
                          {assistantLink}
                        </div>
                        <details className="lr-size-note">
                          <summary>眼镜与学习助手怎样分工</summary>
                          <p>
                            两款眼镜都规划了传感器、主板、天线与电池。距离和光照提醒、作业批改与讲解由学习助手处理。阅读识别还需要同步眼动、头动和前向画面，因此只列入一体镜设计。
                          </p>
                          <p>
                            当前的读写距离与照度来自 Clouclip
                            成人佩戴记录，阅读样片来自 Meta RitW
                            成人研究。样机的测量精度与识别效果仍待实测。
                          </p>
                        </details>
                        <details className="lr-size-note">
                          <summary>尺寸与材料</summary>
                          <p>
                            一体镜约宽 129 mm、高 41 mm，镜腿长 136
                            mm。烟灰色镜框搭配金属铰链。镁合金夹片目标重量约{" "}
                            {clipProduct.weight_g ?? 13} g。
                          </p>
                        </details>
                      </>
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
                        {assistantLink}
                      </div>
                    )}
                  </>
                )}
              </section>
            )}
            {focusedPart === "tof" && <RangeLine project={project} />}
            {!selected && (
              <div className="lr-rail" aria-hidden="true">
                {chapters.map((c) => (
                  <i key={c.id} data-active={c.id === chapter} />
                ))}
              </div>
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
                {guided ? null : failed ? (
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
            <div key={id} id={id}>
              {id === "construction" &&
                steps.map((s, i) => (
                  <div
                    key={i}
                    id={"construction-" + (i + 1)}
                    data-guide-stop=""
                  >
                    {s.cover && (
                      <span
                        className="lr-guide-interior-stop"
                        id={`construction-${i + 1}-inside`}
                      />
                    )}
                  </div>
                ))}
            </div>
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
