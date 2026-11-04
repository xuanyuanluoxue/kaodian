import type { Block, BlockType } from "../../types";

/* 块编辑器的类型元数据：中文名、分组、默认块、摘要与复杂块字段参考。 */

export const BLOCK_LABELS: Record<BlockType, string> = {
  markdown: "Markdown 文本",
  callout: "提示卡",
  columns: "分栏",
  tabs: "标签页",
  steps: "步骤",
  cards: "卡片",
  timeline: "时间线",
  image: "图片",
  video: "视频",
  audio: "音频",
  code: "代码",
  mermaid: "Mermaid 图",
  "math-graph": "数学图",
  sandbox: "实验沙箱",
  divider: "分隔线",
};

export const BLOCK_GROUPS: { label: string; types: BlockType[] }[] = [
  { label: "文本", types: ["markdown", "callout"] },
  { label: "布局", types: ["columns", "tabs", "steps", "cards", "timeline"] },
  { label: "媒体", types: ["image", "video", "audio"] },
  { label: "代码/图", types: ["code", "mermaid", "math-graph"] },
  { label: "其他", types: ["divider", "sandbox"] },
];

/** 复杂块只提供该块对象的 JSON 编辑。 */
export const COMPLEX_TYPES: ReadonlySet<BlockType> = new Set<BlockType>([
  "columns",
  "tabs",
  "steps",
  "cards",
  "timeline",
  "math-graph",
]);

export function isComplexBlock(type: BlockType): boolean {
  return COMPLEX_TYPES.has(type);
}

/** 默认值保持结构合法，添加后可以直接自动保存。 */
export function defaultBlock(type: BlockType): Block {
  switch (type) {
    case "markdown":
      return { type, text: "在这里写 Markdown 内容。" };
    case "callout":
      return { type, tone: "info", title: "提示", text: "在这里写提示内容。" };
    case "columns":
      return {
        type,
        cols: [
          [{ type: "markdown", text: "左栏内容。" }],
          [{ type: "markdown", text: "右栏内容。" }],
        ],
      };
    case "tabs":
      return {
        type,
        items: [
          { label: "标签 1", blocks: [{ type: "markdown", text: "标签页内容。" }] },
          { label: "标签 2", blocks: [{ type: "markdown", text: "第二个标签页。" }] },
        ],
      };
    case "steps":
      return {
        type,
        items: [
          { title: "第一步", text: "说明。" },
          { title: "第二步", text: "说明。" },
        ],
      };
    case "cards":
      return {
        type,
        items: [
          { title: "卡片 1", text: "说明。" },
          { title: "卡片 2", text: "说明。" },
        ],
      };
    case "timeline":
      return {
        type,
        items: [{ time: "第一阶段", title: "标题", text: "说明。" }],
      };
    case "image":
      return {
        type,
        url: "https://example.com/image.png",
        alt: "图片说明",
        caption: "",
        license: "",
      };
    case "video":
      return { type, url: "https://example.com/video.mp4" };
    case "audio":
      return { type, url: "https://example.com/audio.mp3", title: "音频标题" };
    case "code":
      return { type, language: "python", code: "print('hello')" };
    case "mermaid":
      return { type, code: "graph TD\n  A[开始] --> B[结束]" };
    case "math-graph":
      return {
        type,
        spec: {
          height: 320,
          boundingbox: [-5, 5, 5, -5],
          curves: [{ expr: "x^2" }],
        },
      };
    case "sandbox":
      return { type, title: "实验", height: 320, html: "<p>实验内容</p>" };
    case "divider":
      return { type };
  }
}

function clip(value: string, size = 30): string {
  const text = value.replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > size ? `${text.slice(0, size)}…` : text;
}

/** 列表里的一行摘要；不解析 Markdown，只截取文本。 */
export function blockSummary(block: Block): string {
  switch (block.type) {
    case "markdown":
      return clip(block.text) || "空文本";
    case "callout":
      return clip(block.title || block.text) || "空提示";
    case "columns": {
      const count = block.cols.reduce((sum, col) => sum + col.length, 0);
      return `${block.cols.length} 列 · ${count} 个块`;
    }
    case "tabs":
      return `${block.items.length} 个标签`;
    case "steps":
      return `${block.items.length} 个步骤`;
    case "cards":
      return `${block.items.length} 张卡片`;
    case "timeline":
      return `${block.items.length} 个节点`;
    case "image":
      return clip(block.alt || block.caption || block.url) || "图片";
    case "video":
      return clip(block.url) || "视频";
    case "audio":
      return clip(block.title || block.url) || "音频";
    case "code":
      return [block.language, block.title].filter(Boolean).join(" · ") || "代码";
    case "mermaid":
      return "Mermaid 结构图";
    case "math-graph":
      return "交互数学图";
    case "sandbox":
      return clip(block.title ?? "") || "实验页";
    case "divider":
      return "—";
  }
}

/** 复杂块的字段速查；保持短小，不写成长篇文档。 */
export const BLOCK_STRUCTURE: Partial<Record<BlockType, string[]>> = {
  columns: ["cols: Block[][]，2–3 列", "每列都是块数组"],
  tabs: ["items: [{ label, blocks: Block[] }]", "blocks 可再嵌套其它块"],
  steps: ["items: [{ title, text }]"],
  cards: ["items: [{ title, text, link? }]"],
  timeline: ["items: [{ time, title, text }]"],
  "math-graph": [
    "spec: 对象或 JSON 字符串",
    "常用字段：height、boundingbox、curves、points、sliders、annotations",
  ],
};
