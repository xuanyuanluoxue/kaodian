import { useEffect, useRef, useState } from "react";

const STARTERS: Record<string, string> = {
  L01: `#include <stdio.h>

int main() {
    printf("hello, world\\n");
    printf("今天：第 1 天\\n");
    return 0;
}`,
  L02: `#include <stdio.h>

int main() {
    int a = 3.9;
    double b = 3;
    printf("a = %d\\n", a);
    printf("b = %.1f\\n", b);
    printf("int = %zu 字节, double = %zu 字节\\n", sizeof(int), sizeof(double));
    return 0;
}`,
  L03: `#include <stdio.h>

int main() {
    int a = 7, b = 2;
    printf("%d %.1f %d\\n", a / b, (double)a / b, a % b);
    printf("%d %d\\n", 3 < 5, 3 < 5 > 2);
    return 0;
}`,
  L04: `#include <stdio.h>

int main() {
    int n;
    double x;
    scanf("%d %lf", &n, &x);
    printf("n=%03d\\n", n);
    printf("x=%6.2f\\n", x);
    return 0;
}`,
};

const DEFAULT_STARTER = `#include <stdio.h>

int main() {
    printf("hello, world\\n");
    return 0;
}`;

function starterFor(lessonKey?: string): string {
  return (lessonKey && STARTERS[lessonKey]) || DEFAULT_STARTER;
}

interface RunHint {
  line: number | null;
  kind: string;
  message: string;
  reason: string;
  fix: string;
}

interface RunResult {
  ok: boolean;
  stage: "compile" | "run";
  output: string;
  exit_code: number | null;
  compile_output?: string;
  duration_ms?: number;
  hints?: RunHint[];
}

interface CodeTerminalProps {
  subjectId: string;
  pageId: string;
  lessonKey?: string;
  language?: string;
}

export function CodeTerminal({ subjectId, pageId, lessonKey, language = "c" }: CodeTerminalProps) {
  const storageKey = `kaodian:code:${subjectId || "subject"}:${pageId || lessonKey || "free"}`;
  const [code, setCode] = useState(() => localStorage.getItem(storageKey) ?? starterFor(lessonKey));
  const [stdin, setStdin] = useState("");
  const [output, setOutput] = useState("");
  const [status, setStatus] = useState<"idle" | "running" | "ok" | "error">("idle");
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [hints, setHints] = useState<RunHint[]>([]);
  const outRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    fetch("/api/code/status")
      .then((r) => r.json())
      .then((d) => setEnabled(Boolean(d.enabled)))
      .catch(() => setEnabled(false));
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, code);
    } catch {
      /* 隐私模式忽略 */
    }
  }, [code, storageKey]);

  useEffect(() => {
    if (outRef.current) outRef.current.scrollTop = outRef.current.scrollHeight;
  }, [output]);

  async function run() {
    if (status === "running") return;
    setStatus("running");
    setOutput("");
    setDuration(null);
    setHints([]);
    try {
      const res = await fetch("/api/code/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, stdin, language }),
      });
      const data = (await res.json()) as RunResult & { detail?: unknown };
      if (!res.ok) {
        setStatus("error");
        setHints([]);
        setOutput(
          typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? "运行失败"),
        );
        return;
      }
      const text = [data.compile_output?.trim(), data.output]
        .filter((x) => x && String(x).trim())
        .join("\n");
      setOutput(text || "（程序没有输出）");
      setDuration(data.duration_ms ?? null);
      setHints(data.hints ?? []);
      setStatus(data.ok ? "ok" : "error");
    } catch (e) {
      setStatus("error");
      setHints([]);
      setOutput(`请求失败：${String(e)}`);
    }
  }

  function reset() {
    setCode(starterFor(lessonKey));
    setOutput("");
    setStatus("idle");
    setDuration(null);
    setHints([]);
  }

  const statusLabel =
    status === "running"
      ? "编译运行中…"
      : status === "ok"
        ? `通过${duration != null ? ` · ${duration}ms` : ""}`
        : status === "error"
          ? "有错误"
          : "就绪";

  return (
    <aside className="code-panel">
      <div className="code-head">
        <div>
          <b>练习终端</b>
          <span className="muted small"> · gcc · 断网沙箱</span>
        </div>
        <span className={`run-state ${status}`}>{statusLabel}</span>
      </div>

      {enabled === false && (
        <div className="code-disabled">
          代码运行未启用。启动后端时设置 <code>KAODIAN_ALLOW_CODE_RUN=1</code>。
        </div>
      )}

      <textarea
        className="code-editor"
        value={code}
        spellCheck={false}
        onChange={(e) => setCode(e.target.value)}
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
            e.preventDefault();
            run();
          }
        }}
        aria-label="C 代码编辑器"
      />

      <details className="stdin-box">
        <summary>标准输入（scanf 用）</summary>
        <textarea
          value={stdin}
          onChange={(e) => setStdin(e.target.value)}
          placeholder={"例如：7 2.5\\n"}
          spellCheck={false}
        />
      </details>

      <div className="code-buttons">
        <button className="btn btn-primary code-run" onClick={run} disabled={status === "running" || enabled === false}>
          ▶ 运行
        </button>
        <button className="btn btn-ghost code-reset" onClick={reset}>
          还原示例
        </button>
        <span className="muted small">Ctrl+Enter</span>
      </div>

      {hints.length > 0 && (
        <div className="code-hints">
          <div className="hints-head">为什么错</div>
          {hints.map((h, i) => (
            <div className="code-hint" key={`${h.line ?? "run"}-${i}`}>
              <span className="hint-where">
                {h.line == null ? "运行错误" : `第 ${h.line} 行`}
                {h.kind === "warning" && <span className="hint-kind">警告</span>}
              </span>
              <span className="hint-reason">{h.reason}</span>
              {h.fix && <span className="hint-fix">怎么改：{h.fix}</span>}
            </div>
          ))}
        </div>
      )}

      <div className="code-output">
        <div className="out-head">
          <span>输出</span>
          <span>{status === "running" ? "…" : status === "error" ? "stderr" : "stdout"}</span>
        </div>
        <pre ref={outRef}>{output || "点「运行」，或按 Ctrl+Enter。"}</pre>
      </div>
    </aside>
  );
}