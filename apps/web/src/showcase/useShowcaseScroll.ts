import { useCallback, useLayoutEffect, useRef, useState } from "react";
import {
  cameraChapters,
  chapters,
  type Chapter,
  type ScrollTrack,
} from "./product";

type ScrollView = { chapter: Chapter; step: number; reveal: boolean };
const initial: ScrollView = { chapter: "top", step: 0, reveal: false };
const clamp = (n: number) => Math.min(1, Math.max(0, n));

export function useShowcaseScroll() {
  const [view, setView] = useState(initial);
  const last = useRef(initial);
  const track = useRef<ScrollTrack>({ progress: 0 });
  const guidePosition = useRef<number | null>(null);
  const refresh = useRef<(() => void) | null>(null);
  useLayoutEffect(() => {
    const stage = document.querySelector<HTMLElement>(".lr-stage")!;
    const anchors = chapters.map(({ id }) => document.getElementById(id)!);
    const acts = Array.from(
      document.querySelectorAll<HTMLElement>("[data-guide-stop]"),
    );
    let starts: number[] = [],
      actStarts: number[] = [],
      ticket = 0;
    const guide = chapters.findIndex((c) => c.id === "construction");
    const measure = () => {
      const position = window.scrollY;
      const y = position + 0.75; // Native anchor scrolling rounds fractional CSS pixels.
      const inGuide = y >= starts[guide] && y < starts[guide + 1];
      const index = Math.max(0, starts.filter((top) => top <= y).length - 1);
      const fraction = clamp(
        (y - starts[index]) /
          ((starts[index + 1] ?? starts[index] + 1) - starts[index] || 1),
      );
      const step = inGuide
        ? Math.max(0, actStarts.filter((top) => top <= y).length - 1)
        : 0;
      const end = actStarts[step + 1] ?? starts[guide + 1];
      const reveal =
        inGuide && (y - actStarts[step]) / (end - actStarts[step] || 1) >= 0.24;
      // Hold the wearing pose up to the cut. Prices have their own still entry pose.
      const progress =
        index >= guide + 1
          ? cameraChapters.length - 1
          : index >= guide - 1
            ? guide - 1
            : index + fraction;
      const chapter = inGuide
        ? "construction"
        : cameraChapters[Math.round(progress)].id;
      guidePosition.current = inGuide
        ? clamp(
            (position - starts[guide]) / (starts[guide + 1] - starts[guide]),
          )
        : null;
      if (progress !== track.current.progress) {
        track.current.progress = progress;
        const low = Math.floor(progress),
          t = progress - low;
        const isLight = (i: number) =>
          Number(["explore", "specifications"].includes(cameraChapters[i].id));
        const from = isLight(low),
          to = isLight(Math.min(low + 1, cameraChapters.length - 1));
        stage.style.setProperty(
          "--scroll-wash",
          String(from + (to - from) * t * t * (3 - 2 * t)),
        );
        track.current.redraw?.();
      }
      if (
        chapter !== last.current.chapter ||
        step !== last.current.step ||
        reveal !== last.current.reveal
      ) {
        last.current = { chapter, step, reveal };
        setView(last.current);
      }
    };
    const layout = () => {
      const bar = parseFloat(getComputedStyle(anchors[0]).scrollMarginTop) || 0;
      const y = window.scrollY;
      const offset = (el: HTMLElement) =>
        y + el.getBoundingClientRect().top - bar;
      starts = anchors.map(offset);
      actStarts = acts.map(offset);
      measure();
    };
    const schedule = () => {
      if (!ticket)
        ticket = requestAnimationFrame(() => {
          ticket = 0;
          measure();
        });
    };
    const anchor = () => {
      const node = document.getElementById(location.hash.slice(1));
      if (node?.closest(".lr-track"))
        node.scrollIntoView({ behavior: "instant" });
      layout();
    };
    refresh.current = layout;
    anchor();
    const observer = new ResizeObserver(layout);
    observer.observe(stage);
    observer.observe(anchors[guide]);
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", layout);
    window.addEventListener("hashchange", anchor);
    return () => {
      cancelAnimationFrame(ticket);
      observer.disconnect();
      refresh.current = null;
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", layout);
      window.removeEventListener("hashchange", anchor);
    };
  }, []);
  const restoreGuide = useCallback((position: number) => {
    const el = document.getElementById("construction")!;
    const rect = el.getBoundingClientRect();
    const bar = parseFloat(getComputedStyle(el).scrollMarginTop);
    window.scrollTo({
      top: window.scrollY + rect.top - bar + position * rect.height,
      behavior: "instant",
    });
    refresh.current?.();
  }, []);
  return { ...view, track, guidePosition, restoreGuide };
}
