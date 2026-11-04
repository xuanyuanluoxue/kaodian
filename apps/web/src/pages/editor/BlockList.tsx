import type { Block, BlockType } from "../../types";
import { BLOCK_GROUPS, BLOCK_LABELS, blockSummary } from "./blockDefaults";

interface BlockListProps {
  blocks: Block[];
  selected: number;
  onSelect: (index: number) => void;
  onMove: (index: number, direction: -1 | 1) => void;
  onDuplicate: (index: number) => void;
  onDelete: (index: number) => void;
  onAdd: () => void;
}

/** 块列表：序号、类型、摘要与上移/下移/复制/删除。 */
export function BlockList({
  blocks,
  selected,
  onSelect,
  onMove,
  onDuplicate,
  onDelete,
  onAdd,
}: BlockListProps) {
  if (blocks.length === 0) {
    return (
      <div className="block-editor-empty">
        <p>还没有块。添加一个开始编辑。</p>
        <button type="button" className="btn btn-ghost btn-small" onClick={onAdd}>
          添加第一个块
        </button>
      </div>
    );
  }

  return (
    <ol className="block-editor-list" aria-label="块列表">
      {blocks.map((block, index) => {
        const active = index === selected;
        const label = BLOCK_LABELS[block.type] ?? block.type;
        return (
          <li key={index} className={`block-editor-item${active ? " active" : ""}`}>
            <button
              type="button"
              className="block-editor-select"
              onClick={() => onSelect(index)}
              aria-pressed={active}
              aria-label={`选择第 ${index + 1} 个块：${label}`}
            >
              <span className="block-editor-index">{index + 1}</span>
              <span className="block-editor-type">{label}</span>
              <span className="block-editor-summary">{blockSummary(block)}</span>
            </button>
            <div className="block-editor-actions">
              <button
                type="button"
                title="上移"
                aria-label={`上移第 ${index + 1} 个块`}
                disabled={index === 0}
                onClick={() => onMove(index, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                title="下移"
                aria-label={`下移第 ${index + 1} 个块`}
                disabled={index === blocks.length - 1}
                onClick={() => onMove(index, 1)}
              >
                ↓
              </button>
              <button
                type="button"
                title="复制"
                aria-label={`复制第 ${index + 1} 个块`}
                onClick={() => onDuplicate(index)}
              >
                ⧉
              </button>
              <button
                type="button"
                className="is-danger"
                title="删除"
                aria-label={`删除第 ${index + 1} 个块`}
                onClick={() => onDelete(index)}
              >
                ✕
              </button>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

interface BlockPickerProps {
  onAdd: (type: BlockType) => void;
  onClose: () => void;
}

/** 按分组展示可添加的块类型。 */
export function BlockPicker({ onAdd, onClose }: BlockPickerProps) {
  return (
    <div className="block-picker" role="group" aria-label="添加块">
      <div className="block-picker-head">
        <strong>添加块</strong>
        <button type="button" className="block-picker-close" onClick={onClose} aria-label="收起">
          ✕
        </button>
      </div>
      {BLOCK_GROUPS.map((group) => (
        <div className="block-picker-group" key={group.label}>
          <span className="block-picker-label">{group.label}</span>
          <div className="block-picker-types">
            {group.types.map((type) => (
              <button
                key={type}
                type="button"
                className="block-picker-item"
                onClick={() => onAdd(type)}
              >
                {BLOCK_LABELS[type]}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
