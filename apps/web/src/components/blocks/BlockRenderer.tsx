import { Markdown } from "../Markdown";
import { Mermaid } from "../Mermaid";
import { CalloutBlock } from "./CalloutBlock";
import { CardsBlock } from "./CardsBlock";
import { CodeBlock } from "./CodeBlock";
import { ColumnsBlock } from "./ColumnsBlock";
import { MathGraphBlock } from "./MathGraphBlock";
import { AudioBlock, ImageBlock, VideoBlock } from "./MediaBlocks";
import { SandboxBlock } from "./SandboxBlock";
import { StepsBlock } from "./StepsBlock";
import { TabsBlock } from "./TabsBlock";
import { TimelineBlock } from "./TimelineBlock";
import type { Block } from "../../types";

interface Props {
  block: Block;
  depth?: number;
  pageId?: string;
  index?: number;
}

const MAX_DEPTH = 3;

function UnknownBlock({ type, detail }: { type: string; detail?: string }) {
  return (
    <div className="block-unknown">
      未支持的块：{type}
      {detail ? <span className="block-unknown-detail">{detail}</span> : null}
    </div>
  );
}

/** 按 type 分发；未知块降级为提示条，不白屏。 */
export function BlockRenderer({ block, depth = 0, pageId, index }: Props) {
  if (depth > MAX_DEPTH) {
    return <UnknownBlock type={block.type} detail="嵌套超过 3 层" />;
  }

  const render = (child: Block) => <BlockRenderer block={child} depth={depth + 1} />;

  switch (block.type) {
    case "markdown":
      return <Markdown>{block.text}</Markdown>;
    case "callout":
      return <CalloutBlock block={block} />;
    case "columns":
      return <ColumnsBlock block={block} render={render} />;
    case "tabs":
      return <TabsBlock block={block} render={render} />;
    case "steps":
      return <StepsBlock block={block} />;
    case "cards":
      return <CardsBlock block={block} />;
    case "timeline":
      return <TimelineBlock block={block} />;
    case "image":
      return <ImageBlock block={block} />;
    case "video":
      return <VideoBlock block={block} />;
    case "audio":
      return <AudioBlock block={block} />;
    case "code":
      return <CodeBlock block={block} />;
    case "mermaid":
      return <Mermaid chart={block.code} />;
    case "math-graph":
      return <MathGraphBlock block={block} />;
    case "sandbox":
      // 后端保证 sandbox 只在顶层；这里再挡一次，避免嵌套 iframe。
      return depth > 0 ? (
        <UnknownBlock type="sandbox" detail="实验页只能放在顶层" />
      ) : (
        <SandboxBlock block={block} pageId={pageId} index={index} />
      );
    case "divider":
      return <hr className="block-divider" />;
    default: {
      const raw = block as { type?: unknown };
      return <UnknownBlock type={typeof raw.type === "string" ? raw.type : "unknown"} />;
    }
  }
}
