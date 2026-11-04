import type { ReactNode } from "react";
import type { Block, ColumnsBlock as ColumnsBlockData } from "../../types";

interface Props {
  block: ColumnsBlockData;
  render: (block: Block) => ReactNode;
}

/* 分栏：2–3 列，窄屏由 CSS 收回单栏。 */
export function ColumnsBlock({ block, render }: Props) {
  const cols = block.cols.slice(0, 3);
  return (
    <div className={`block-columns is-${cols.length}`}>
      {cols.map((col, i) => (
        <div className="block-column" key={i}>
          {col.map((child, j) => (
            <div className="block-column-item" key={j}>
              {render(child)}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
