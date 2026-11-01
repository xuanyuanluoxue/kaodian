import katex from "katex";
import { useMemo } from "react";

/**
 * 极简文本渲染：支持 `行内代码`、$行内公式$、换行。
 * 不解析 HTML，避免 AI 生成内容注入。
 */
export function MathText({ text }: { text: string }) {
  const nodes = useMemo(() => {
    const parts = text.split(/(`[^`]*`|\$[^$]+\$|\n)/g).filter((p) => p !== "");
    return parts.map((part, i) => {
      if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
        return (
          <code key={i} className="inline-code">
            {part.slice(1, -1)}
          </code>
        );
      }
      if (part.startsWith("$") && part.endsWith("$") && part.length > 2) {
        return (
          <span
            key={i}
            dangerouslySetInnerHTML={{
              __html: katex.renderToString(part.slice(1, -1), { throwOnError: false }),
            }}
          />
        );
      }
      if (part === "\n") return <br key={i} />;
      return <span key={i}>{part}</span>;
    });
  }, [text]);
  return <>{nodes}</>;
}