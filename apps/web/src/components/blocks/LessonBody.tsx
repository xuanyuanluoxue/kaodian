import type { CSSProperties } from "react";
import { Markdown } from "../Markdown";
import { BlockRenderer } from "./BlockRenderer";
import type { PageDetail } from "../../types";

/** 命名强调色只映射到全局 token，内容不能写任意 CSS。 */
const ACCENT_TOKENS: Record<string, string> = {
  math: "var(--theme-math-accent)",
  computer: "var(--theme-computer-accent)",
  english: "var(--theme-english-accent)",
  politics: "var(--theme-politics-accent)",
};

const DENSITY: Record<string, string> = {
  compact: "0.82",
  comfortable: "1",
};

const FONT: Record<string, string> = {
  sans: "var(--sans)",
  serif: "var(--serif)",
};

const HEX = /^#[0-9A-Fa-f]{3,8}$/;

function accentValue(accent?: string): string | undefined {
  if (!accent) return undefined;
  if (HEX.test(accent)) return accent;
  return ACCENT_TOKENS[accent];
}

interface Props {
  page: PageDetail;
}

/**
 * 讲义正文入口：块页渲染 BlockRenderer，普通页保持原来的 Markdown，
 * 外层统一承载 layout / theme。
 */
export function LessonBody({ page }: Props) {
  const blocks = page.blocks;
  const useBlocks =
    page.format === "blocks" && Array.isArray(blocks) && blocks.length > 0;
  const theme = page.theme ?? {};
  const style = {
    "--lesson-accent": accentValue(theme.accent) ?? "var(--accent)",
    "--lesson-density": DENSITY[theme.density ?? ""] ?? DENSITY.comfortable,
    "--lesson-font": FONT[theme.font ?? ""] ?? FONT.sans,
  } as CSSProperties;

  return (
    <div
      className={`lesson-body ${useBlocks ? "is-blocks" : "is-markdown"}`}
      data-layout={page.layout || "article"}
      style={style}
    >
      {useBlocks ? (
        blocks.map((block, i) => (
          <BlockRenderer key={i} block={block} pageId={page.id} index={i} />
        ))
      ) : (
        <Markdown>{page.body}</Markdown>
      )}
    </div>
  );
}
