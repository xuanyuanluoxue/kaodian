import type { StepsBlock as StepsBlockData } from "../../types";

/* 有序步骤。 */
export function StepsBlock({ block }: { block: StepsBlockData }) {
  return (
    <ol className="block-steps">
      {block.items.map((item, i) => (
        <li className="block-step" key={`${item.title}-${i}`}>
          <div className="block-step-title">{item.title}</div>
          <p className="block-step-text">{item.text}</p>
        </li>
      ))}
    </ol>
  );
}
