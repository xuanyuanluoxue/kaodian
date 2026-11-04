import type { CodeBlock as CodeBlockData } from "../../types";

/* 代码块：语言标签 + 原生 pre/code，React 已转义内容。 */
export function CodeBlock({ block }: { block: CodeBlockData }) {
  return (
    <figure className="block-code">
      <div className="block-code-head">
        <span className="block-code-title">{block.title || "代码"}</span>
        <span className="block-code-lang">{block.language}</span>
      </div>
      <pre>
        <code className={`language-${block.language}`}>{block.code}</code>
      </pre>
    </figure>
  );
}
