import type { CSSProperties } from "react";
import type { SandboxBlock as SandboxBlockData } from "../../types";

const DEFAULT_HEIGHT = 420;
const MIN_HEIGHT = 200;
const MAX_HEIGHT = 900;

function clampHeight(height?: number): number {
  if (typeof height !== "number" || !Number.isFinite(height)) return DEFAULT_HEIGHT;
  return Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, Math.round(height)));
}

/**
 * 隔离实验页：只给 allow-scripts，不加 allow-same-origin，
 * 因此 iframe 读不到应用的 localStorage / Cookie / API。
 */
export function SandboxBlock({
  block,
  pageId,
  index,
}: {
  block: SandboxBlockData;
  pageId?: string;
  index?: number;
}) {
  const height = clampHeight(block.height);
  const style = { "--sandbox-height": `${height}px` } as CSSProperties;
  return (
    <figure className="block-sandbox" style={style}>
      <div className="block-sandbox-bar">
        <span className="block-sandbox-badge">实验页</span>
        <span className="block-sandbox-title">{block.title || "隔离运行，脚本无法访问应用数据"}</span>
      </div>
      <iframe
        title={block.title || "实验页"}
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
        src={pageId != null && index != null ? `/sandbox/${pageId}/${index}` : undefined}
        srcDoc={pageId != null && index != null ? undefined : block.html}
        loading="lazy"
      />
    </figure>
  );
}
