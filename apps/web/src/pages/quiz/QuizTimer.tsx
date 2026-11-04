import { useSyncExternalStore } from "react";
import { mmss } from "../../lib/format";
import type { Clock } from "./useQuizSession";

/* 计时单独成组件：每秒只重渲染这里，不带着整道题一起刷。 */

interface Props {
  clock: Clock;
  limit: number | null;
  paused: boolean;
  onTogglePause: () => void;
}

export function QuizTimer({ clock, limit, paused, onTogglePause }: Props) {
  const active = useSyncExternalStore(clock.subscribe, clock.getSnapshot, clock.getSnapshot);
  const remaining = limit ? Math.max(0, limit - active) : null;
  return (
    <div className={`timer ${paused ? "paused" : ""}`} role="timer">
      <span className="timer-label">{paused ? "已暂停" : limit ? "剩余" : "已用"}</span>
      <b>{limit ? mmss(remaining ?? 0) : mmss(active)}</b>
      <button className="link-btn" type="button" onClick={onTogglePause} aria-pressed={paused}>
        {paused ? "继续" : "暂停"}
      </button>
    </div>
  );
}
