import { useEffect, useId, useRef, useState } from "react";

type Theme = "light" | "dark";

let mermaidLoader: Promise<typeof import("mermaid")> | null = null;
function loadMermaid() {
  if (!mermaidLoader) mermaidLoader = import("mermaid");
  return mermaidLoader;
}

export function Mermaid({ chart }: { chart: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const [theme, setTheme] = useState<Theme>(
    document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");

  useEffect(() => {
    const obs = new MutationObserver(() => {
      setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    let alive = true;
    setError("");
    loadMermaid()
      .then((mod) => {
        const mermaid = mod.default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: theme === "dark" ? "dark" : "default",
          // Mermaid 12：htmlLabels 必须放根级，放 flowchart 里会被忽略
          htmlLabels: false,
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif',
          flowchart: { useMaxWidth: true, wrappingWidth: 300, htmlLabels: false },
        });
        const id = `mmd-${uid}-${theme}-${Math.random().toString(36).slice(2, 7)}`;
        return mermaid.render(id, chart).then(({ svg }) => {
          if (alive && host.current) host.current.innerHTML = svg;
        });
      })
      .catch((e) => {
        if (alive) setError(String(e));
      });
    return () => {
      alive = false;
    };
  }, [chart, theme, uid]);

  return (
    <div className="mermaid-block">
      <div ref={host} />
      {error && <pre className="mermaid-fallback">{chart}</pre>}
    </div>
  );
}