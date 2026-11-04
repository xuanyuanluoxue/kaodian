import katex from "katex";
import { useMemo, type ReactNode } from "react";

/**
 * 极简文本渲染：支持 ``` 代码块、`行内代码`、$行内公式$、换行。
 * 不解析 HTML，避免 AI 生成内容注入。
 */
export function MathText({ text }: { text: string }) {
  const nodes = useMemo(() => {
    const out: ReactNode[] = [];
    const fence = /```[a-zA-Z0-9_+-]*\r?\n([\s\S]*?)```/g;
    let last = 0;
    let match: RegExpExecArray | null;
    let key = 0;

    const inline = (chunk: string) => {
      const parts = chunk.split(/(`[^`]*`|\$[^$]+\$|\n)/g).filter((p) => p !== "");
      return parts.map((part) => {
        const k = key++;
        if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
          return (
            <code key={k} className="inline-code">
              {part.slice(1, -1)}
            </code>
          );
        }
        if (part.startsWith("$") && part.endsWith("$") && part.length > 2) {
          return (
            <span
              key={k}
              dangerouslySetInnerHTML={{
                __html: katex.renderToString(part.slice(1, -1), { throwOnError: false }),
              }}
            />
          );
        }
        if (part === "\n") return <br key={k} />;
        return <span key={k}>{part}</span>;
      });
    };

    while ((match = fence.exec(text))) {
      if (match.index > last) out.push(...inline(text.slice(last, match.index)));
      out.push(
        <pre key={key++} className="question-code">
          <code>{match[1].replace(/\n$/, "")}</code>
        </pre>,
      );
      last = match.index + match[0].length;
    }
    if (last < text.length) out.push(...inline(text.slice(last)));
    return out;
  }, [text]);
  return <>{nodes}</>;
}
