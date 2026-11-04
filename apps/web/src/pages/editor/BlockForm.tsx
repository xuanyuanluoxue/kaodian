import { useState } from "react";
import type { Block, CalloutTone } from "../../types";
import { BLOCK_STRUCTURE, isComplexBlock } from "./blockDefaults";

interface BlockFormProps {
  block: Block;
  onChange: (block: Block) => void;
}

const TONES: { value: CalloutTone; label: string }[] = [
  { value: "info", label: "信息" },
  { value: "warn", label: "注意" },
  { value: "danger", label: "危险" },
  { value: "success", label: "成功" },
];

interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  mono?: boolean;
}

function TextField({ label, value, onChange, placeholder, mono }: TextFieldProps) {
  return (
    <label className="block-form-field">
      <span>{label}</span>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={mono ? "is-mono" : undefined}
      />
    </label>
  );
}

interface TextAreaProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  mono?: boolean;
  rows?: number;
}

function TextArea({ label, value, onChange, placeholder, mono, rows = 6 }: TextAreaProps) {
  return (
    <label className="block-form-field">
      <span>{label}</span>
      <textarea
        value={value}
        rows={rows}
        placeholder={placeholder}
        spellCheck={false}
        onChange={(e) => onChange(e.target.value)}
        className={mono ? "is-mono" : undefined}
      />
    </label>
  );
}

/** 复杂块：只编辑当前块对象的 JSON；非法 JSON 不向上更新。 */
function ComplexBlockForm({ block, onChange }: BlockFormProps) {
  const [text, setText] = useState(() => JSON.stringify(block, null, 2));
  const [error, setError] = useState("");
  const structure = BLOCK_STRUCTURE[block.type];

  function handleChange(value: string) {
    setText(value);
    try {
      const parsed: unknown = JSON.parse(value);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        throw new Error("块必须是一个 JSON 对象");
      }
      const type = (parsed as { type?: unknown }).type;
      if (type !== block.type) {
        throw new Error(`type 必须保持为 "${block.type}"`);
      }
      setError("");
      onChange(parsed as Block);
    } catch (e) {
      setError(`JSON 解析失败：${e instanceof Error ? e.message : String(e)}`);
    }
  }

  return (
    <div className="block-form">
      <p className="block-form-hint">这个块结构较复杂，直接编辑块 JSON；修改内容实时进入预览。</p>
      <label className="block-form-field">
        <span>块 JSON</span>
        <textarea
          className="is-mono block-form-json"
          value={text}
          rows={14}
          spellCheck={false}
          onChange={(e) => handleChange(e.target.value)}
          aria-label="块 JSON"
        />
      </label>
      {error && <div className="block-form-error">{error}</div>}
      {structure && (
        <details className="block-form-structure">
          <summary>结构说明</summary>
          <ul>
            {structure.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/** 简单块的结构化表单；复杂块委托给 ComplexBlockForm。 */
export function BlockForm({ block, onChange }: BlockFormProps) {
  if (isComplexBlock(block.type)) {
    return <ComplexBlockForm block={block} onChange={onChange} />;
  }

  switch (block.type) {
    case "markdown":
      return (
        <div className="block-form">
          <TextArea
            label="Markdown"
            value={block.text}
            onChange={(text) => onChange({ ...block, text })}
            mono
            rows={10}
          />
        </div>
      );

    case "callout":
      return (
        <div className="block-form">
          <div className="block-form-row">
            <label className="block-form-field">
              <span>语气</span>
              <select
                value={block.tone}
                onChange={(e) =>
                  onChange({ ...block, tone: e.target.value as CalloutTone })
                }
              >
                {TONES.map((tone) => (
                  <option key={tone.value} value={tone.value}>
                    {tone.label}
                  </option>
                ))}
              </select>
            </label>
            <TextField
              label="标题（可选）"
              value={block.title ?? ""}
              onChange={(title) => onChange({ ...block, title })}
            />
          </div>
          <TextArea
            label="正文"
            value={block.text}
            onChange={(text) => onChange({ ...block, text })}
            rows={4}
          />
        </div>
      );

    case "code":
      return (
        <div className="block-form">
          <div className="block-form-row">
            <TextField
              label="语言"
              value={block.language}
              onChange={(language) => onChange({ ...block, language })}
              placeholder="python"
              mono
            />
            <TextField
              label="标题（可选）"
              value={block.title ?? ""}
              onChange={(title) => onChange({ ...block, title })}
            />
          </div>
          <TextArea
            label="代码"
            value={block.code}
            onChange={(code) => onChange({ ...block, code })}
            mono
            rows={10}
          />
        </div>
      );

    case "mermaid":
      return (
        <div className="block-form">
          <TextArea
            label="Mermaid 代码"
            value={block.code}
            onChange={(code) => onChange({ ...block, code })}
            mono
            rows={10}
          />
        </div>
      );

    case "image":
      return (
        <div className="block-form">
          <TextField
            label="图片 URL"
            value={block.url}
            onChange={(url) => onChange({ ...block, url })}
            placeholder="/media/<pack>/... 或 https://"
            mono
          />
          <div className="block-form-row">
            <TextField
              label="替代文本 alt"
              value={block.alt ?? ""}
              onChange={(alt) => onChange({ ...block, alt })}
            />
            <TextField
              label="说明 caption"
              value={block.caption ?? ""}
              onChange={(caption) => onChange({ ...block, caption })}
            />
            <TextField
              label="许可 license"
              value={block.license ?? ""}
              onChange={(license) => onChange({ ...block, license })}
            />
          </div>
        </div>
      );

    case "video":
      return (
        <div className="block-form">
          <TextField
            label="视频 URL"
            value={block.url}
            onChange={(url) => onChange({ ...block, url })}
            placeholder="/media/<pack>/... 或 https://"
            mono
          />
          <TextField
            label="封面 poster（可选）"
            value={block.poster ?? ""}
            onChange={(poster) => onChange({ ...block, poster })}
            mono
          />
        </div>
      );

    case "audio":
      return (
        <div className="block-form">
          <TextField
            label="音频 URL"
            value={block.url}
            onChange={(url) => onChange({ ...block, url })}
            placeholder="/media/<pack>/... 或 https://"
            mono
          />
          <TextField
            label="标题（可选）"
            value={block.title ?? ""}
            onChange={(title) => onChange({ ...block, title })}
          />
        </div>
      );

    case "sandbox":
      return (
        <div className="block-form">
          <div className="block-form-row">
            <TextField
              label="标题（可选）"
              value={block.title ?? ""}
              onChange={(title) => onChange({ ...block, title })}
            />
            <label className="block-form-field">
              <span>高度（200–900）</span>
              <input
                type="number"
                min={200}
                max={900}
                value={block.height ?? ""}
                onChange={(e) =>
                  onChange({
                    ...block,
                    height: e.target.value === "" ? undefined : Number(e.target.value),
                  })
                }
              />
            </label>
          </div>
          <TextArea
            label="HTML"
            value={block.html}
            onChange={(html) => onChange({ ...block, html })}
            mono
            rows={12}
          />
          <p className="block-form-hint">实验页，脚本不能访问应用数据。</p>
        </div>
      );

    case "divider":
      return (
        <div className="block-form">
          <p className="block-form-hint">分隔线没有可编辑字段。</p>
        </div>
      );

    default:
      return (
        <div className="block-form">
          <p className="block-form-hint">未支持的块类型。</p>
        </div>
      );
  }
}
