import type { CalloutBlock as CalloutBlockData } from "../../types";

/* 提示卡：tone 只映射到已有 token，不读取内容里的样式。 */
export function CalloutBlock({ block }: { block: CalloutBlockData }) {
  return (
    <aside className={`block-callout is-${block.tone}`}>
      {block.title ? <div className="block-callout-title">{block.title}</div> : null}
      <div className="block-callout-body">{block.text}</div>
    </aside>
  );
}
