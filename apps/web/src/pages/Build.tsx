import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { errorText } from "../lib/format";
import { useQuestionTypes } from "../lib/useQuestionTypes";
import type { OutlineNode, Subject } from "../types";

export function Build() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subjectId, setSubjectId] = useState(params.get("subject") || "");
  const [nodes, setNodes] = useState<OutlineNode[]>([]);
  const [codes, setCodes] = useState<Set<string>>(new Set());
  const [types, setTypes] = useState<Set<string>>(new Set());
  const [count, setCount] = useState(10);
  const [mode, setMode] = useState<"practice" | "exam">("practice");
  const [minutes, setMinutes] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { types: questionTypes, loading: typesLoading } = useQuestionTypes();

  useEffect(() => {
    api
      .subjects()
      .then((list) => {
        setSubjects(list);
        setSubjectId((current) =>
          current && list.some((s) => s.id === current) ? current : list[0]?.id || "",
        );
      })
      .catch((e) => setError(errorText(e)));
  }, []);

  useEffect(() => {
    if (!questionTypes.length) return;
    setTypes((current) => {
      if (current.size) return current;
      const auto = questionTypes.filter((t) => t.grading === "auto").map((t) => t.id);
      return new Set(auto.length ? auto : questionTypes.map((t) => t.id));
    });
  }, [questionTypes]);

  useEffect(() => {
    setCodes(new Set());
    if (!subjectId) {
      setNodes([]);
      return;
    }
    api
      .outline(subjectId)
      .then(setNodes)
      .catch((e) => setError(errorText(e)));
  }, [subjectId]);

  const sections = useMemo(() => {
    const map = new Map<string, OutlineNode[]>();
    nodes.forEach((n) => {
      const key = n.section || "未分组";
      map.set(key, [...(map.get(key) || []), n]);
    });
    return [...map.entries()];
  }, [nodes]);

  const available = useMemo(
    () => nodes.filter((n) => codes.has(n.code)).reduce((sum, n) => sum + n.question_count, 0),
    [nodes, codes],
  );

  function toggleCode(code: string) {
    const next = new Set(codes);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setCodes(next);
  }

  function toggleSection(list: OutlineNode[]) {
    const next = new Set(codes);
    const allOn = list.every((n) => next.has(n.code));
    list.forEach((n) => (allOn ? next.delete(n.code) : next.add(n.code)));
    setCodes(next);
  }

  function toggleType(t: string) {
    const next = new Set(types);
    if (next.has(t)) next.delete(t);
    else next.add(t);
    setTypes(next);
  }

  async function start() {
    setBusy(true);
    setError("");
    try {
      const quiz = await api.buildQuiz({
        title: title || undefined,
        mode,
        count,
        time_limit: minutes ? Number(minutes) * 60 : null,
        filters: {
          subject_id: subjectId,
          codes: [...codes],
          types: [...types],
          exclude_days: mode === "practice" ? 2 : 0,
        },
      });
      navigate(`/quiz/${quiz.id}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  const subject = subjects.find((s) => s.id === subjectId);

  return (
    <div className="page build-page">
      <div className="build-main">
        <div className="page-head">
          <p className="eyebrow">组卷</p>
          <h1>挑一个范围，开始</h1>
          <p className="lede">选中考点后，题目从题库里随机抽；最近做过的会先避开。</p>
          <p className="hint">更常用的方式：在对话里让 Agent 出题，链接会直接发给你。</p>
        </div>

        {error && <div className="alert">{error}</div>}

        <div className="field">
          <label>科目</label>
          <div className="chips">
            {subjects.map((s) => (
              <button
                key={s.id}
                className={`chip ${subjectId === s.id ? "on" : ""}`}
                onClick={() => setSubjectId(s.id)}
              >
                {s.short}
                <span className="chip-num">{s.question_count}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <div className="field-head">
            <label>考点</label>
            <span className="muted small">
              {codes.size ? `已选 ${codes.size} 条` : "不选 = 全科目"}
            </span>
          </div>
          {sections.map(([section, list]) => (
            <div className="section-block" key={section}>
              <div className="section-title">
                <span>{section}</span>
                <button className="link-btn" onClick={() => toggleSection(list)}>
                  全选 / 反选
                </button>
              </div>
              <div className="chips">
                {list.map((n) => (
                  <button
                    key={n.code}
                    className={`chip chip-code ${codes.has(n.code) ? "on" : ""} ${n.kind === "training" ? "muted-chip" : ""}`}
                    onClick={() => toggleCode(n.code)}
                    title={n.title}
                  >
                    {n.code}
                    <span className="chip-num">{n.question_count}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="field">
          <label>题型</label>
          <div className="chips">
            {questionTypes.map((t) => (
              <button
                key={t.id}
                className={`chip ${types.has(t.id) ? "on" : ""}`}
                onClick={() => toggleType(t.id)}
              >
                {t.label}
              </button>
            ))}
            {typesLoading && <span className="muted small">正在读取题型…</span>}
          </div>
        </div>

        <div className="field-row">
          <div className="field">
            <label>题量</label>
            <input
              type="number"
              min={1}
              max={100}
              value={count}
              onChange={(e) => setCount(Math.max(1, Math.min(100, Number(e.target.value) || 1)))}
            />
          </div>
          <div className="field">
            <label>时限（分钟，可空）</label>
            <input
              type="number"
              min={1}
              placeholder={mode === "exam" ? "默认每题 1.5 分钟" : "不限"}
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
            />
          </div>
          <div className="field">
            <label>练习名称（可空）</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="自动生成" />
          </div>
        </div>

        <div className="field">
          <label>模式</label>
          <div className="chips">
            <button className={`chip ${mode === "practice" ? "on" : ""}`} onClick={() => setMode("practice")}>
              练习 · 即时看解析
            </button>
            <button className={`chip ${mode === "exam" ? "on" : ""}`} onClick={() => setMode("exam")}>
              考试 · 交卷后统一批
            </button>
          </div>
        </div>
      </div>

      <aside className="rail">
        <div className="card summary">
          <div className="card-kicker">本卷</div>
          <h3>{subject?.short || "—"}</h3>
          <dl className="summary-list">
            <div>
              <dt>考点</dt>
              <dd>{codes.size ? `${codes.size} 条` : "全科目"}</dd>
            </div>
            <div>
              <dt>可用题</dt>
              <dd className={available < count ? "warn-text" : ""}>{codes.size ? available : subject?.question_count ?? 0}</dd>
            </div>
            <div>
              <dt>题量</dt>
              <dd>{count}</dd>
            </div>
            <div>
              <dt>时限</dt>
              <dd>{minutes ? `${minutes} 分钟` : mode === "exam" ? "自动" : "不限"}</dd>
            </div>
          </dl>
          {codes.size > 0 && available < count && (
            <p className="hint warn">
              可用题只有 {available} 道，组卷会自动缩小到实际数量。
            </p>
          )}
          {types.size === 0 && <p className="hint warn">至少选一种题型。</p>}
          <button className="btn btn-primary btn-block" onClick={start} disabled={busy || types.size === 0}>
            {busy ? "正在组卷…" : "开始"}
          </button>
          <p className="hint">练习模式会避开最近 2 天做过的题。</p>
        </div>
      </aside>
    </div>
  );
}