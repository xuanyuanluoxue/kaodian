import { useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import MathFigure, { type MathSpec } from "./MathFigure";
import { Mermaid } from "./Mermaid";

const FIGURE_BLOCK = /```(mermaid|math-graph)[ \t]*\r?\n([\s\S]*?)```/g;

const components: Components = {
  img: ({ src, alt, title }) => (
    <span className="md-figure">
      <img src={typeof src === "string" ? src : undefined} alt={alt ?? ""} title={title} />
      {alt ? <span className="md-caption">{alt}</span> : null}
    </span>
  ),
};

function MathGraph({ code }: { code: string }) {
  const spec = useMemo<MathSpec | null>(() => {
    try {
      const parsed = JSON.parse(code) as unknown;
      if (typeof parsed !== "object" || parsed === null) return null;
      return parsed as MathSpec;
    } catch {
      return null;
    }
  }, [code]);

  if (!spec) {
    return <pre className="math-figure-fallback">{code}</pre>;
  }
  return <MathFigure spec={spec} />;
}

export function Markdown({ children }: { children: string }) {
  const blocks: Array<{ kind: "md" | "mermaid" | "math-graph"; text: string }> = [];
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = FIGURE_BLOCK.exec(children))) {
    if (match.index > last) {
      blocks.push({ kind: "md", text: children.slice(last, match.index) });
    }
    blocks.push({
      kind: match[1] === "math-graph" ? "math-graph" : "mermaid",
      text: match[2].trim(),
    });
    last = match.index + match[0].length;
  }
  if (last < children.length) {
    blocks.push({ kind: "md", text: children.slice(last) });
  }

  return (
    <div className="prose">
      {blocks.map((block, i) => {
        if (block.kind === "mermaid") return <Mermaid key={i} chart={block.text} />;
        if (block.kind === "math-graph") return <MathGraph key={i} code={block.text} />;
        return (
          <ReactMarkdown
            key={i}
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[rehypeKatex]}
            components={components}
          >
            {block.text}
          </ReactMarkdown>
        );
      })}
    </div>
  );
}
