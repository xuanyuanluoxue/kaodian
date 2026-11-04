import { useId, useState } from "react";
import type { ReactNode } from "react";
import type { Block, TabsBlock as TabsBlockData } from "../../types";

interface Props {
  block: TabsBlockData;
  render: (block: Block) => ReactNode;
}

/* 标签页：本地 state 切换，内容在面板里按块渲染。 */
export function TabsBlock({ block, render }: Props) {
  const uid = useId();
  const [active, setActive] = useState(0);
  const items = block.items;
  const current = Math.min(active, Math.max(items.length - 1, 0));

  return (
    <div className="block-tabs">
      <div className="block-tabs-bar" role="tablist" aria-label="内容切换">
        {items.map((item, i) => (
          <button
            key={`${item.label}-${i}`}
            type="button"
            role="tab"
            id={`${uid}-tab-${i}`}
            aria-selected={i === current}
            aria-controls={`${uid}-panel-${i}`}
            className="block-tab"
            onClick={() => setActive(i)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {items.map((item, i) => (
        <div
          key={`${item.label}-panel-${i}`}
          role="tabpanel"
          id={`${uid}-panel-${i}`}
          aria-labelledby={`${uid}-tab-${i}`}
          className="block-tabs-panel"
          hidden={i !== current}
        >
          {item.blocks.map((child, j) => (
            <div className="block-tabs-item" key={j}>
              {render(child)}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
