import { ApiError } from "../api";

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} 分钟`;
  const h = Math.floor(m / 60);
  return `${h} 小时 ${m % 60} 分`;
}

export function mmss(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function percent(part: number, total: number): string {
  if (!total) return "—";
  return `${Math.round((part / total) * 100)}%`;
}

export function errorText(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}
