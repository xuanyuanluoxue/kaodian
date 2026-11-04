import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { errorText } from "../lib/format";
import type { LibraryStats, PageDetail, PageSummary, Progress, QuizSummary, Subject } from "../types";
import { ConsolePath } from "./console/ConsolePath";
import { ConsoleReader } from "./console/ConsoleReader";
import { useReadingTimer } from "./console/useReadingTimer";

/* 控制台容器：数据加载 + 路由参数，路径 / 阅读分别交给子组件。 */
export function Console() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [pages, setPages] = useState<PageSummary[]>([]);
  const [page, setPage] = useState<PageDetail | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [library, setLibrary] = useState<LibraryStats | null>(null);
  const [quizzes, setQuizzes] = useState<QuizSummary[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subjectsLoaded, setSubjectsLoaded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [completing, setCompleting] = useState(false);

  const selectedId = params.get("page");
  const subjectId = params.get("subject") || subjects[0]?.id || "";
  const reading = !!selectedId;
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;
  useReadingTimer(selectedId);

  // 首屏分区降级：任一接口失败只影响对应区域，不整页空
  useEffect(() => {
    let alive = true;
    void (async () => {
      const [pagesR, progressR, quizzesR, subjectsR, libraryR] = await Promise.allSettled([
        api.pages(),
        api.progress(),
        api.quizzes(6),
        api.subjects(),
        api.library(),
      ]);
      if (!alive) return;
      const failed: string[] = [];
      if (pagesR.status === "fulfilled") setPages(pagesR.value);
      else failed.push(`课程（${errorText(pagesR.reason)}）`);
      if (progressR.status === "fulfilled") setProgress(progressR.value);
      else failed.push(`进度（${errorText(progressR.reason)}）`);
      if (quizzesR.status === "fulfilled") setQuizzes(quizzesR.value);
      else failed.push(`练习单（${errorText(quizzesR.reason)}）`);
      if (subjectsR.status === "fulfilled") setSubjects(subjectsR.value);
      else failed.push(`科目（${errorText(subjectsR.reason)}）`);
      if (libraryR.status === "fulfilled") setLibrary(libraryR.value);
      else failed.push(`题库统计（${errorText(libraryR.reason)}）`);
      setSubjectsLoaded(true);
      if (failed.length) setError(`部分内容加载失败：${failed.join("；")}`);
    })();
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    setPage(null);
    if (!selectedId) return;
    let alive = true;
    api
      .page(selectedId)
      .then((p) => {
        if (alive && selectedRef.current === selectedId) setPage(p);
      })
      .catch((e) => alive && setError(errorText(e)));
    return () => {
      alive = false;
    };
  }, [selectedId]);

  const openPage = useCallback(
    (pageId: string, subject: string) => setParams({ subject, page: pageId }),
    [setParams],
  );

  const selectSubject = useCallback((id: string) => setParams({ subject: id }), [setParams]);

  async function practice() {
    if (!page) return;
    setBusy(true);
    setError("");
    try {
      const session = await api.createAgentSession(`控制台 · ${page.title}`);
      const quiz = await api.buildQuiz({
        title: `${page.title} · 练习`,
        mode: "practice",
        count: 6,
        agent_session_id: session.id,
        filters: {
          ...(page.subject_id ? { subject_id: page.subject_id } : {}),
          codes: page.outline_codes,
        },
      });
      navigate(`/quiz/${quiz.id}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  async function complete() {
    const target = page;
    if (!target || target.id !== selectedRef.current) return;
    setCompleting(true);
    try {
      const res = await api.completePage(target.id);
      setPages((prev) => prev.map((p) => (p.id === target.id ? { ...p, completed: true, xp: res.xp } : p)));
      const [fresh, prog] = await Promise.allSettled([api.page(target.id), api.progress()]);
      if (prog.status === "fulfilled") setProgress(prog.value);
      if (fresh.status === "fulfilled" && selectedRef.current === target.id) setPage(fresh.value);
      const failed = [fresh, prog].find((r) => r.status === "rejected");
      if (failed && failed.status === "rejected") setError(errorText(failed.reason));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setCompleting(false);
    }
  }

  if (reading) {
    return (
      <ConsoleReader
        page={page}
        pages={pages}
        subjects={subjects}
        progress={progress}
        quizzes={quizzes}
        error={error}
        busy={busy}
        completing={completing}
        onSelectPage={(id) => openPage(id, page?.subject_id || subjectId)}
        onComplete={complete}
        onPractice={practice}
      />
    );
  }

  return (
    <ConsolePath
      subjects={subjects}
      subjectsLoaded={subjectsLoaded}
      subjectId={subjectId}
      pages={pages}
      progress={progress}
      library={library}
      quizzes={quizzes}
      error={error}
      onSelectSubject={selectSubject}
      onOpenPage={openPage}
    />
  );
}
