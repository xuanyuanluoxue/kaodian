import { useCallback, useEffect, useRef } from "react";

/* 阅读计时：只看被选中课程的阅读页；页面可见 + 90 秒内有操作才累计，
   每 15 秒把增量发给 /api/activity，离开时用 sendBeacon 兜底。 */

const READING_FLUSH_SECONDS = 15;
const READING_IDLE_MS = 90_000;
const READING_EVENTS = ["keydown", "click", "scroll", "touchstart", "mousemove", "pointerdown"] as const;

function postActivity(pageId: string, seconds: number) {
  if (seconds <= 0) return;
  const payload = JSON.stringify({ page_id: pageId, seconds, source: "page" });
  if (navigator.sendBeacon) {
    const blob = new Blob([payload], { type: "application/json" });
    if (navigator.sendBeacon("/api/activity", blob)) return;
  }
  fetch("/api/activity", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
    keepalive: true,
  }).catch(() => {});
}

export function useReadingTimer(pageId: string | null) {
  const pending = useRef(0);
  const pageRef = useRef<string | null>(pageId);
  const lastAction = useRef(Date.now());

  // 始终按“当前页”上报；切换页面前先 flush 旧页
  const flush = useCallback(() => {
    const id = pageRef.current;
    const seconds = pending.current;
    if (!id || seconds <= 0) return;
    pending.current = 0;
    postActivity(id, seconds);
  }, []);

  useEffect(() => {
    pageRef.current = pageId;
    pending.current = 0;
    lastAction.current = Date.now();
    if (!pageId) return;

    const bump = () => {
      lastAction.current = Date.now();
    };
    const onVisibility = () => {
      if (document.hidden) flush();
      else lastAction.current = Date.now();
    };

    READING_EVENTS.forEach((event) =>
      window.addEventListener(event, bump, { passive: true } as AddEventListenerOptions),
    );
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", flush);
    window.addEventListener("beforeunload", flush);

    const timer = setInterval(() => {
      if (document.hidden || Date.now() - lastAction.current > READING_IDLE_MS) {
        flush();
        return;
      }
      pending.current += 1;
      if (pending.current >= READING_FLUSH_SECONDS) flush();
    }, 1000);

    return () => {
      clearInterval(timer);
      READING_EVENTS.forEach((event) => window.removeEventListener(event, bump));
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", flush);
      window.removeEventListener("beforeunload", flush);
      flush();
    };
  }, [pageId, flush]);
}
