import ReactMarkdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { Mermaid } from "./Mermaid";

const MERMAID_BLOCK = /```mermaid[ \t]*\n([\s\S]*?)```/g;

const components: Components = {
  img: ({ src, alt, title }) => (
    <span className="md-figure">
      <img src={typeof src === "string" ? src : undefined} alt={alt ?? ""} title={title} loading="lazy" />
      {alt ? <span className="md-caption">{alt}</span> : null}
    </span>
  ),
};

export function Markdown({ children }: { children: string }) {
  const blocks: Array<{ kind: "md" | "mermaid"; text: string }> = [];
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = MERMAID_BLOCK.exec(children))) {
    if (match.index > last) {
      blocks.push({ kind: "md", text: children.slice(last, match.index) });
    }
    blocks.push({ kind: "mermaid", text: match[1].trim() });
    last = match.index + match[0].length;
  }
  if (last < children.length) {
    blocks.push({ kind: "md", text: children.slice(last) });
  }

  return (
    <div className="prose">
      {blocks.map((block, i) =>
        block.kind === "mermaid" ? (
          <Mermaid key={i} chart={block.text} />
        ) : (
          <ReactMarkdown
            key={i}
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[rehypeKatex]}
            components={components}
          >
            {block.text}
          </ReactMarkdown>
        ),
      )}
    </div>
  );
}