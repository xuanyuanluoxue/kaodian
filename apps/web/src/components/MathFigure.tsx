import { useEffect, useRef, useState } from "react";

export interface MathSpec {
  height?: number;
  boundingbox?: [number, number, number, number];
  alt?: string;
  sliders?: {
    name: string;
    min: number;
    max: number;
    step: number;
    value: number;
    label?: string;
  }[];
  curves?: { expr: string; domain?: [number, number]; color?: string }[];
  points?: { name: string; at: [string, string]; color?: string }[];
  tangent?: { curve: number; at: string; color?: string };
  annotations?: { at: [string, string]; text: string }[];
}

type Theme = "light" | "dark";

interface JXGElement {
  Value?: () => number;
}

interface JXGBoard {
  create: (
    type: string,
    parents: unknown[],
    attributes?: Record<string, unknown>,
  ) => JXGElement;
}

interface JXGLike {
  JSXGraph: {
    initBoard: (host: HTMLElement, attributes: Record<string, unknown>) => JXGBoard;
    freeBoard: (board: JXGBoard) => void;
  };
}

const IDENT = /^[A-Za-z_$][\w$]*$/;

let jxgLoader: Promise<JXGLike> | null = null;
function loadJXG(): Promise<JXGLike> {
  if (!jxgLoader) {
    jxgLoader = import("jsxgraph").then(
      (mod) =>
        ((mod as unknown as { default?: JXGLike }).default ??
          mod) as unknown as JXGLike,
    );
  }
  return jxgLoader;
}

function assertNames(names: string[]) {
  for (const name of names) {
    if (!IDENT.test(name)) throw new Error(`非法滑块变量名：${name}`);
  }
}

/**
 * 数学写法里的 `^` 在 JS 中是按位异或（1^2 === 3），
 * 这里统一转成幂运算，让 spec 可以写 `a*x^2`。
 */
function mathExpr(expr: string) {
  return expr.replace(/\^/g, "**");
}

/** 把表达式编译成以 x 为自变量的函数，滑块变量在调用时读取最新值。 */
function curveEvaluator(
  expr: string,
  names: string[],
  values: () => number[],
): (x: number) => number {
  assertNames(names);
  const fn = new Function(
    ...names,
    "x",
    `"use strict"; return (${mathExpr(expr)});`,
  ) as (...args: number[]) => unknown;
  return (x: number) => Number(fn(...values(), x));
}

/** 编译只依赖滑块变量的数值表达式（用于坐标、切线位置等）。 */
function atEvaluator(
  expr: string,
  names: string[],
  values: () => number[],
): () => number {
  assertNames(names);
  const fn = new Function(
    ...names,
    `"use strict"; return (${mathExpr(expr)});`,
  ) as (...args: number[]) => unknown;
  return () => Number(fn(...values()));
}

function mountBoard(
  JXG: JXGLike,
  host: HTMLElement,
  spec: MathSpec,
  theme: Theme,
): () => void {
  const dark = theme === "dark";
  const axisColor = dark ? "#59605a" : "#c9c4b7";
  const textColor = dark ? "#cbd0c7" : "#5c594f";
  const accent = dark ? "#7cc9b4" : "#1d6b5c";

  const bbox = spec.boundingbox ?? [-5, 5, 5, -5];
  const [x1, y1, x2, y2] = bbox;

  const board = JXG.JSXGraph.initBoard(host, {
    boundingbox: bbox,
    axis: true,
    showCopyright: false,
    showNavigation: false,
    showInfobox: false,
    keepaspectratio: false,
    backgroundcolor: "transparent",
    pan: { enabled: true, needTwoFingers: true },
    zoom: { enabled: true, needTwoFingers: true },
    defaultAxes: {
      x: {
        strokeColor: axisColor,
        highlightStrokeColor: axisColor,
        label: { strokeColor: textColor },
        ticks: {
          strokeColor: axisColor,
          label: { strokeColor: textColor },
        },
      },
      y: {
        strokeColor: axisColor,
        highlightStrokeColor: axisColor,
        label: { strokeColor: textColor },
        ticks: {
          strokeColor: axisColor,
          label: { strokeColor: textColor },
        },
      },
    },
  });

  try {
    const sliderSpecs = spec.sliders ?? [];
    const names = sliderSpecs.map((s) => s.name);
    const sliderEls: Record<string, JXGElement> = {};
    const values = () =>
      names.map((name) => sliderEls[name]?.Value?.() ?? 0);

    // 滑块排在 boundingbox 底部，横向铺开，纵向依次堆叠
    if (sliderSpecs.length > 0) {
      const width = Math.abs(x2 - x1) || 1;
      const height = Math.abs(y1 - y2) || 1;
      const left = x1 + width * 0.06;
      const right = x2 - width * 0.2;
      const rowGap = Math.min(height * 0.12, 0.6);
      sliderSpecs.forEach((slider, i) => {
        const y = y2 + rowGap * (sliderSpecs.length - i) * 1.15;
        sliderEls[slider.name] = board.create(
          "slider",
          [[left, y], [right, y], [slider.min, slider.value, slider.max]],
          {
            name: slider.label || slider.name,
            snapWidth: slider.step,
            strokeColor: axisColor,
            fillColor: accent,
            highlightFillColor: accent,
            highlightStrokeColor: axisColor,
            label: { strokeColor: textColor, fontSize: 13 },
          },
        );
      });
    }

    const curveSpecs = spec.curves ?? [];
    const curves = curveSpecs.map((curve) =>
      curveEvaluator(curve.expr, names, values),
    );
    curveSpecs.forEach((curve, i) => {
      board.create(
        "functiongraph",
        [curves[i], curve.domain?.[0] ?? x1, curve.domain?.[1] ?? x2],
        {
          strokeColor: curve.color || accent,
          strokeWidth: 2,
          highlight: false,
        },
      );
    });

    for (const point of spec.points ?? []) {
      const evalX = atEvaluator(point.at[0], names, values);
      const evalY = atEvaluator(point.at[1], names, values);
      board.create("point", [() => evalX(), () => evalY()], {
        name: point.name,
        size: 3,
        color: point.color || accent,
        highlightFillColor: point.color || accent,
        label: { strokeColor: textColor, fontSize: 13 },
      });
    }

    if (spec.tangent) {
      const { curve, at, color } = spec.tangent;
      const f = curves[curve];
      if (!f) throw new Error(`切线引用了不存在的曲线：${curve}`);
      const atX = atEvaluator(at, names, values);
      const tangentY = (x0: number, dx: number) => {
        const h = 1e-5;
        const slope = (f(x0 + h) - f(x0 - h)) / (2 * h);
        return f(x0) + slope * dx;
      };
      const p1 = board.create(
        "point",
        [() => atX() - 1.2, () => tangentY(atX(), -1.2)],
        { visible: false, withLabel: false },
      );
      const p2 = board.create(
        "point",
        [() => atX() + 1.2, () => tangentY(atX(), 1.2)],
        { visible: false, withLabel: false },
      );
      board.create("line", [p1, p2], {
        strokeColor: color || accent,
        strokeWidth: 1.5,
        dash: 2,
        highlight: false,
      });
    }

    for (const note of spec.annotations ?? []) {
      const noteX = atEvaluator(note.at[0], names, values)();
      const noteY = atEvaluator(note.at[1], names, values)();
      board.create("text", [noteX, noteY, note.text], {
        fontSize: 12,
        strokeColor: textColor,
        anchorX: "left",
        anchorY: "middle",
        fixed: true,
      });
    }
  } catch (error) {
    JXG.JSXGraph.freeBoard(board);
    throw error;
  }

  return () => JXG.JSXGraph.freeBoard(board);
}

export default function MathFigure({ spec }: { spec: MathSpec }) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const [theme, setTheme] = useState<Theme>(
    document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );
  const height = spec.height ?? 340;
  const specKey = JSON.stringify(spec);

  useEffect(() => {
    const observeTheme = () => {
      setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
    };
    const obs = new MutationObserver(observeTheme);
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    let dispose: (() => void) | undefined;
    setError("");

    loadJXG()
      .then((JXG) => {
        if (cancelled || !host.current) return;
        try {
          dispose = mountBoard(JXG, host.current, spec, theme);
        } catch (e) {
          setError(String(e));
        }
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });

    return () => {
      cancelled = true;
      dispose?.();
    };
    // specKey 让内联对象每次渲染的引用变化不会重建 board
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specKey, theme]);

  if (error) {
    return (
      <figure className="math-figure">
        <pre className="math-figure-fallback">{JSON.stringify(spec, null, 2)}</pre>
      </figure>
    );
  }

  return (
    <figure className="math-figure">
      <div
        ref={host}
        className="math-figure-host"
        style={{ height }}
        role="img"
        aria-label={spec.alt || "交互数学图"}
      />
      {spec.alt ? <figcaption className="math-figure-caption">{spec.alt}</figcaption> : null}
    </figure>
  );
}
