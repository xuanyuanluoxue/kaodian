import { ApiError } from "../../api";
import { errorText } from "../../lib/format";
import type { Block, PageDraftInput, PageTheme } from "../../types";

/* PageEditor 的保存辅助：把编辑快照合成草稿请求体。 */

export function parseBlocks(text: string): Block[] {
  const parsed: unknown = JSON.parse(text);
  if (!Array.isArray(parsed)) throw new Error("blocks 必须是数组");
  return parsed as Block[];
}

export function themeOf(accent: string, density: string, font: string): PageTheme | null {
  const theme: PageTheme = {};
  if (accent) theme.accent = accent;
  if (density) theme.density = density;
  if (font) theme.font = font;
  return Object.keys(theme).length ? theme : null;
}

export interface EditorSnapshot {
  isBlocks: boolean;
  content: string;
  blocksText: string;
  layout: string;
  accent: string;
  density: string;
  font: string;
  version: number;
}

export type BuiltPayload =
  | { ok: true; body: PageDraftInput }
  | { ok: false; error: string };

/** 保存 / pagehide 共用：从最新编辑状态合成草稿请求体。 */
export function buildPayload(snapshot: EditorSnapshot): BuiltPayload {
  const theme = themeOf(snapshot.accent, snapshot.density, snapshot.font);
  if (snapshot.isBlocks) {
    try {
      const blocks = parseBlocks(snapshot.blocksText);
      return {
        ok: true,
        body: {
          blocks,
          layout: snapshot.layout,
          theme,
          base_version: snapshot.version,
        },
      };
    } catch (e) {
      return {
        ok: false,
        error: `JSON 解析失败：${e instanceof Error ? e.message : String(e)}`,
      };
    }
  }
  return {
    ok: true,
    body: {
      body: snapshot.content,
      layout: snapshot.layout,
      theme,
      base_version: snapshot.version,
    },
  };
}

export function conflictText(e: unknown): string {
  if (e instanceof ApiError && e.status === 422) {
    const detail = e.detail as { message?: unknown; errors?: unknown } | null;
    if (
      detail &&
      typeof detail === "object" &&
      typeof detail.message === "string" &&
      Array.isArray(detail.errors)
    ) {
      const errors = detail.errors.filter((item): item is string => typeof item === "string");
      if (errors.length) return `${detail.message}：${errors.join("；")}`;
    }
  }
  return errorText(e);
}
