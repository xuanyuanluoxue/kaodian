import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { errorText, formatDuration, percent } from "../lib/format";
import type { HeatmapDay, SubjectStats, TypeStats } from "../types";

const RANGES = [7, 30, 90] as const;
type Range = (typeof RANGES)[number];

/** 周一起算的星期缩写，只有奇数行显示，避免拥挤。 */
const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

function parseDay(value: string): Date {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y || 1970, (m || 1) - 1, d || 1);
}

function localDayKey(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function duration(seconds: number): string {
  return seconds > 0 ? formatDuration(Math.round(seconds)) : "0 分钟";
}

function barWidth(part: number, total: number): string {
  if (!total) return "0%";
  return `${Math.round((part / total) * 100)}%`;
}

/** 5 档：0 / <15 分 / <45 分 / <90 分 / 更长。 */
function heatLevel(seconds: number): number {
  if (!seconds) return 0;
  const minutes = seconds / 60;
  if (minutes < 15) return 1;
  if (minutes < 45) return 2;
  if (minutes < 90) return 3;
  return 4;
}

function heatTip(day: HeatmapDay): string {
  const time = day.seconds > 0 ? duration(day.seconds) : "没有学习";
  return `${day.date} · ${time} · ${day.answered} 题`;
}

export function Stats() {
  const [range, setRange] = useState<Range>(30);
  const [heat, setHeat] = useState<HeatmapDay[]>([]);
  const [subjects, setSubjects] = useState<SubjectStats[]>([]);
  const [types, setTypes] = useState<TypeStats[]>([]);
  const [heatLoading, setHeatLoading] = useState(true);
  const [loading, setLoading] = useState(true);
  const [heatError, setHeatError] = useState("");
  const [error, setError] = useState("");

  const todayKey = useMemo(() => localDayKey(new Date()), []);

  useEffect(() => {
    let alive = true;
    api
      .statsHeatmap(90)
      .then((rows) => alive && setHeat(rows))
      .catch((e) => alive && setHeatError(errorText(e)))
      .finally(() => alive && setHeatLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    void Promise.allSettled([api.statsSubjects(range), api.statsTypes(range)]).then(
      ([subjectR, typeR]) => {
        if (!alive) return;
        const failed: string[] = [];
        if (subjectR.status === "fulfilled") setSubjects(subjectR.value);
        else failed.push(`科目（${errorText(subjectR.reason)}）`);
        if (typeR.status === "fulfilled") setTypes(typeR.value);
        else failed.push(`题型（${errorText(typeR.reason)}）`);
        setError(failed.length ? `部分统计加载失败：${failed.join("；")}` : "");
        setLoading(false);
      },
    );
    return () => {
      alive = false;
    };
  }, [range]);

  const recent = useMemo(() => heat.slice(-range), [heat, range]);

  const totalSeconds = useMemo(() => {
    if (recent.length) return recent.reduce((n, d) => n + d.seconds, 0);
    return subjects.reduce((n, s) => n + s.seconds, 0);
  }, [recent, subjects]);
  const totalAnswered = subjects.reduce((n, s) => n + s.answered, 0);
  const totalCorrect = subjects.reduce((n, s) => n + s.correct, 0);
  const totalAttempts = subjects.reduce((n, s) => n + s.attempts, 0);
  const hasData = totalSeconds > 0 || totalAnswered > 0 || totalAttempts > 0;

  /** 7 行（周一…周日）× 周列；首尾补空格，每天对齐到自己的星期行。 */
  const heatColumns = useMemo(() => {
    if (!heat.length) return [] as (HeatmapDay | null)[][];
    const cells: (HeatmapDay | null)[] = [];
    const lead = (parseDay(heat[0].date).getDay() + 6) % 7;
    for (let i = 0; i < lead; i += 1) cells.push(null);
    cells.push(...heat);
    while (cells.length % 7) cells.push(null);
    const columns: (HeatmapDay | null)[][] = [];
    for (let i = 0; i < cells.length; i += 7) columns.push(cells.slice(i, i + 7));
    return columns;
  }, [heat]);

  const monthMarks = useMemo(() => {
    let last = "";
    return heatColumns.map((column) => {
      const first = column.find((d): d is HeatmapDay => Boolean(d));
      const month = first ? first.date.slice(0, 7) : "";
      if (!month || month === last) return null;
      last = month;
      return `${Number(month.slice(5, 7))}月`;
    });
  }, [heatColumns]);

  const typeRows = useMemo(
    () => [...types].sort((a, b) => b.answered - a.answered),
    [types],
  );

  const heatGridStyle = {
    gridTemplateColumns: `repeat(${Math.max(heatColumns.length, 1)}, var(--heat-cell))`,
  } as const;

  return (
    <div className="page stats-page">
      <div className="page-head">
        <p className="eyebrow">统计</p>
        <h1>学习投入与正确率</h1>
        <p className="lede">时长来自作答计时和讲义阅读，按本地日期归档。</p>
      </div>

      <div className="stats-toolbar">
        <div className="chips" role="group" aria-label="时间范围">
          {RANGES.map((d) => (
            <button
              key={d}
              className={`chip ${range === d ? "on" : ""}`}
              aria-pressed={range === d}
              onClick={() => setRange(d)}
            >
              近 {d} 天
            </button>
          ))}
        </div>
        <span className="muted small">{loading ? "加载中…" : `热力图固定看近 90 天`}</span>
      </div>

      {heatError && <div className="alert">热力图加载失败：{heatError}</div>}
      {error && <div className="alert">{error}</div>}

      <section className={`stats-summary ${loading ? "is-stale" : ""}`}>
        <div className="stat">
          <span>近 {range} 天总时长</span>
          <b>{heatLoading ? "…" : duration(totalSeconds)}</b>
        </div>
        <div className="stat">
          <span>总作答</span>
          <b>
            {totalAnswered}
            <small> 题</small>
          </b>
        </div>
        <div className="stat">
          <span>总正确率</span>
          <b>{percent(totalCorrect, totalAnswered)}</b>
        </div>
      </section>

      {!loading && !heatLoading && !hasData && !error && !heatError && (
        <div className="empty-state stats-empty">
          <p>还没有学习记录。答一套题、读一节课，这里就有数据了。</p>
          <div className="stats-empty-actions">
            <Link to="/build" className="btn btn-primary">
              去组一套题
            </Link>
            <Link to="/console" className="btn">
              打开控制台
            </Link>
          </div>
        </div>
      )}

      <section className="section">
        <div className="section-head">
          <h2>学习热力图</h2>
          <span className="muted small">近 90 天 · 颜色越深投入越多</span>
        </div>
        <div className="card heatmap-card">
          {heatLoading ? (
            <p className="muted small">正在加载热力图…</p>
          ) : heatColumns.length ? (
            <div className="heatmap-body">
              <div className="heat-months" style={heatGridStyle} aria-hidden="true">
                {monthMarks.map((mark, i) => (
                  <span key={i}>{mark}</span>
                ))}
              </div>
              <div className="heat-weekdays" aria-hidden="true">
                {WEEKDAYS.map((label, i) => (
                  <span key={label} className={i % 2 === 0 ? "" : "is-blank"}>
                    {i % 2 === 0 ? label : ""}
                  </span>
                ))}
              </div>
              <div
                className="heat-grid"
                style={heatGridStyle}
                role="img"
                aria-label={`近 90 天学习热力图，共 ${heat.length} 天`}
              >
                {heatColumns.map((column, ci) =>
                  column.map((day, ri) => {
                    if (!day) {
                      return <span key={`${ci}-${ri}`} className="heat-cell is-blank" />;
                    }
                    return (
                      <span
                        key={day.date}
                        className={`heat-cell l${heatLevel(day.seconds)} ${
                          day.date === todayKey ? "is-today" : ""
                        }`}
                        title={heatTip(day)}
                      />
                    );
                  }),
                )}
              </div>
              <div className="heat-legend" aria-hidden="true">
                <span className="muted small">少</span>
                {[0, 1, 2, 3, 4].map((level) => (
                  <span key={level} className={`heat-cell l${level}`} />
                ))}
                <span className="muted small">多</span>
              </div>
            </div>
          ) : (
            <p className="muted small">
              {heatError ? "热力图加载失败。" : "还没有热力图数据。"}
            </p>
          )}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>科目对比</h2>
          <span className="muted small">近 {range} 天</span>
        </div>
        <div className={`card stats-list ${loading ? "is-stale" : ""}`}>
          {!subjects.length && loading ? (
            <p className="muted small">正在加载科目统计…</p>
          ) : subjects.length ? (
            subjects.map((s) => (
              <div key={s.subject_id} className="stat-row">
                <div className="stat-row-head">
                  <span
                    className="dot"
                    style={{ background: s.color || "var(--accent)" }}
                    aria-hidden="true"
                  />
                  <h3>{s.short || s.name}</h3>
                  <span className="stat-row-meta muted small">
                    {duration(s.seconds)} · {s.answered} 题
                    {s.attempts ? ` · ${s.attempts} 次练习` : ""}
                  </span>
                </div>
                <div className="stat-track">
                  <span
                    className="stat-fill"
                    style={{
                      width: barWidth(s.correct, s.answered),
                      background: s.color || "var(--accent)",
                    }}
                  />
                </div>
                <div className="stat-row-foot muted small">
                  <span>正确率 {percent(s.correct, s.answered)}</span>
                  <span>{s.answered ? `${s.correct} / ${s.answered} 对` : "暂无作答"}</span>
                </div>
              </div>
            ))
          ) : (
            <p className="muted small">
              {error ? "科目统计加载失败。" : "还没有科目数据。"}
            </p>
          )}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>题型正确率</h2>
          <span className="muted small">近 {range} 天</span>
        </div>
        <div className={`card stats-list ${loading ? "is-stale" : ""}`}>
          {typeRows.length ? (
            typeRows.map((t) => (
              <div key={t.type} className="type-row">
                <div className="stat-row-head">
                  <h3>{t.label || t.type}</h3>
                  <span className="stat-row-meta muted small">
                    {t.answered} 题 · {percent(t.correct, t.answered)}
                  </span>
                </div>
                <div className="stat-track">
                  <span
                    className="stat-fill"
                    style={{ width: barWidth(t.correct, t.answered) }}
                  />
                </div>
              </div>
            ))
          ) : (
            <p className="muted small">
              {loading ? "正在加载题型统计…" : error ? "题型统计加载失败。" : "这段时间还没有作答记录。"}
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
