import type { TimelineBlock as TimelineBlockData } from "../../types";

/* 时间线。 */
export function TimelineBlock({ block }: { block: TimelineBlockData }) {
  return (
    <ol className="block-timeline">
      {block.items.map((item, i) => (
        <li className="block-timeline-item" key={`${item.time}-${i}`}>
          <div className="block-timeline-time">{item.time}</div>
          <div className="block-timeline-title">{item.title}</div>
          <p className="block-timeline-text">{item.text}</p>
        </li>
      ))}
    </ol>
  );
}
