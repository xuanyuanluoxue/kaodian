import MathFigure, { type MathSpec } from "../MathFigure";
import type { MathGraphBlock as MathGraphBlockData } from "../../types";

function parseSpec(spec: MathGraphBlockData["spec"]): MathSpec | null {
  let value: unknown = spec;
  if (typeof spec === "string") {
    try {
      value = JSON.parse(spec) as unknown;
    } catch {
      return null;
    }
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  return value as MathSpec;
}

/* JSON 块里的交互数学图，复用现有 MathFigure。 */
export function MathGraphBlock({ block }: { block: MathGraphBlockData }) {
  const spec = parseSpec(block.spec);
  if (!spec) {
    return (
      <pre className="math-figure-fallback">
        {typeof block.spec === "string" ? block.spec : JSON.stringify(block.spec, null, 2)}
      </pre>
    );
  }
  return <MathFigure spec={spec} />;
}
