import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { LessonBody } from "../components/blocks/LessonBody";
import { errorText } from "../lib/format";
import type {
  Block,
  PageDetail,
  PageDraftInput,
  PageDraftResponse,
  PageTheme,
} from "../types";

/* 网页编辑器：左侧改草稿，右侧复用 LessonBody 实时预览。 */

const LAYOUTS = [
  { value: "article", label: "文章" },
  { value: "wide", label: "宽屏" },
  { value: "split", label: "两栏" },
  { value: "slides", label: "幻灯片" },
  { value: "dashboard", label: "仪表盘" },
];

const ACCENTS = [
  { value: "math", label: "数学蓝" },
  { value: "computer", label: "计算机绿" },
  { value: "english", label: "英语金" },
  { value: "politics", label: "政治红" },
];

const DENSITIES = [
  { value: "comfortable", label: "舒适" },
  { value: "compact", label: "紧凑" },
];

const HEX = /^#[0-9A-Fa-f]{3,8}$/;

type SaveState = "saved" | "dirty" | "saving" | "conflict" | "error";

const STATUS_TEXT: Record<SaveState, string> = {
  saved: "已保存",
  dirty: "未保存",
  saving: "保存中…",
  conflict: "有冲突",
  error: "保存失败",
};

type BuiltPayload =
  | { ok: true; body: PageDraftInput }
  | { ok: false; error: string };

function parseBlocks(text: string): Block[] {
  const parsed: unknown = JSON.parse(text);
  if (!Array.isArray(parsed)) throw new Error("blocks 必须是数组");
  return parsed as Block[];
}

function themeOf(accent: string, density: string, font: string): PageTheme | null {
  const theme: PageTheme = {};
  if (accent) theme.accent = accent;
  if (density) theme.density = density;
  if (font) theme.font = font;
  return Object.keys(theme).length ? theme : null;
}

function conflictText(e: unknown): string {
  if (e instanceof ApiError && e.status === 422) {
    const detail = e.detail as { message?: unknown; errors?: unknown } | null;
    if (
      detail &&
      typeof detail === "object" &&
      typeof detail.message === "string" &&
      Array.isArray(detail.errors)
    ) {
      const errors = detail.errors.filter((item): item is string => typeof item === "string");
      if (errors.length) return `${detail.message}：${errors.join("；")}`;
    }
  }
  return errorText(e);
}

interface EditorSnapshot {
  isBlocks: boolean;
  content: string;
  blocksText: string;
  layout: string;
  accent: string;
  density: string;
  font: string;
  version: number;
}

/** 保存 / pagehide 共用：从最新编辑状态合成草稿请求体。 */
function buildPayload(snapshot: EditorSnapshot): BuiltPayload {
  const theme = themeOf(snapshot.accent, snapshot.density, snapshot.font);
  if (snapshot.isBlocks) {
    try {
      const blocks = parseBlocks(snapshot.blocksText);
      return {
        ok: true,
        body: {
          blocks,
          layout: snapshot.layout,
          theme,
          base_version: snapshot.version,
        },
      };
    } catch (e) {
      return {
        ok: false,
        error: `JSON 解析失败：${e instanceof Error ? e.message : String(e)}`,
      };
    }
  }
  return {
    ok: true,
    body: {
      body: snapshot.content,
      layout: snapshot.layout,
      theme,
      base_version: snapshot.version,
    },
  };
}

export function PageEditor() {
  const { pageId = "" } = useParams();
  const navigate = useNavigate();

  const [page, setPage] = useState<PageDetail | null>(null);
  const [content, setContent] = useState("");
  const [blocksText, setBlocksText] = useState("[]");
  const [previewBlocks, setPreviewBlocks] = useState<Block[] | null>(null);
  const [layout, setLayout] = useState("article");
  const [accent, setAccent] = useState("");
  const [density, setDensity] = useState("");
  const [font, setFont] = useState("");
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<SaveState>("saved");
  const [error, setError] = useState("");
  const [jsonError, setJsonError] = useState("");
  const [remote, setRemote] = useState(false);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [discarding, setDiscarding] = useState(false);

  const isBlocks =
    page?.format === "blocks" || (page?.format == null && Array.isArray(page?.blocks));

  // 最新编辑值放 ref：防抖/离开页面时不必依赖闭包里的旧 state。
  const formatRef = useRef(false);
  const contentRef = useRef("");
  const blocksTextRef = useRef("[]");
  const layoutRef = useRef("article");
  const accentRef = useRef("");
  const densityRef = useRef("");
  const fontRef = useRef("");
  const pageRef = useRef<PageDetail | null>(null);
  const versionRef = useRef(0);

  const dirtyRef = useRef(false);
  const conflictRef = useRef(false);
  const editRevRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const savePromiseRef = useRef<Promise<boolean> | null>(null);
  const lastVersionRef = useRef<number | null>(null);
  const pendingRemoteRef = useRef<number | null>(null);
  const aliveRef = useRef(true);

  const applyPayload = useCallback((resp: PageDraftResponse) => {
    const { page: nextPage, draft } = resp;
    const nextBlocks = draft ? draft.blocks : (nextPage.blocks ?? null);
    const nextBlocksText = JSON.stringify(nextBlocks ?? [], null, 2);
    const theme = draft ? draft.theme : nextPage.theme;
    const nextVersion = draft?.version ?? 0;
    const nextContent = draft ? (draft.body ?? "") : (nextPage.body || "");
    const nextLayout = draft?.layout || nextPage.layout || "article";
    const nextAccent = theme?.accent ?? "";
    const nextDensity = theme?.density ?? "";
    const nextFont = theme?.font ?? "";
    const nextIsBlocks =
      nextPage.format === "blocks" ||
      (nextPage.format == null && Array.isArray(nextPage.blocks));

    pageRef.current = nextPage;
    contentRef.current = nextContent;
    blocksTextRef.current = nextBlocksText;
    layoutRef.current = nextLayout;
    accentRef.current = nextAccent;
    densityRef.current = nextDensity;
    fontRef.current = nextFont;
    formatRef.current = nextIsBlocks;
    versionRef.current = nextVersion;

    setPage(nextPage);
    setContent(nextContent);
    setBlocksText(nextBlocksText);
    setPreviewBlocks(nextBlocks);
    setLayout(nextLayout);
    setAccent(nextAccent);
    setDensity(nextDensity);
    setFont(nextFont);
    setVersion(nextVersion);
    lastVersionRef.current = draft?.version ?? null;
    pendingRemoteRef.current = null;
    dirtyRef.current = false;
    conflictRef.current = false;
    setJsonError("");
    setError("");
    setRemote(false);
    setState("saved");
  }, []);

  // 首屏：已有草稿优先，否则用页面已发布内容。
  useEffect(() => {
    let alive = true;
    aliveRef.current = true;
    api
      .pageDraft(pageId)
      .then((resp) => {
        if (!alive) return;
        applyPayload(resp);
        setLoading(false);
      })
      .catch((e) => {
        if (!alive) return;
        setError(errorText(e));
        setLoading(false);
      });
    return () => {
      alive = false;
      aliveRef.current = false;
    };
  }, [pageId, applyPayload]);

  function currentSnapshot(): EditorSnapshot {
    return {
      isBlocks: formatRef.current,
      content: contentRef.current,
      blocksText: blocksTextRef.current,
      layout: layoutRef.current,
      accent: accentRef.current,
      density: densityRef.current,
      font: fontRef.current,
      version: versionRef.current,
    };
  }

  function scheduleSave() {
    if (conflictRef.current) return;
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      void saveNow(false);
    }, 1200);
  }

  async function saveNow(ensureDraft = false): Promise<boolean> {
    if (!pageRef.current) return false;
    if (savePromiseRef.current) {
      const ok = await savePromiseRef.current;
      if (!ok) return false;
      return saveNow(ensureDraft);
    }
    if (conflictRef.current) {
      setState("conflict");
      return false;
    }
    if (!dirtyRef.current && !(ensureDraft && versionRef.current === 0)) return true;

    const built = buildPayload(currentSnapshot());
    if (!built.ok) {
      setJsonError(built.error);
      setError("");
      setState("error");
      return false;
    }

    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const revision = editRevRef.current;
    setState("saving");
    setError("");
    setJsonError("");

    const target = pageRef.current;
    const run = (async () => {
      try {
        const resp = await api.savePageDraft(target.id, built.body);
        const nextVersion = resp.draft?.version ?? versionRef.current;
        versionRef.current = nextVersion;
        setVersion(nextVersion);
        lastVersionRef.current = resp.draft?.version ?? null;
        if (resp.page) setPage(resp.page);
        if (resp.page) pageRef.current = resp.page;
        if (pendingRemoteRef.current !== null && pendingRemoteRef.current <= nextVersion) {
          pendingRemoteRef.current = null;
          setRemote(false);
        }
        if (editRevRef.current === revision) {
          dirtyRef.current = false;
          setState("saved");
        } else {
          setState("dirty");
          scheduleSave();
        }
        return true;
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          conflictRef.current = true;
          setState("conflict");
          setError("");
        } else {
          setState("error");
          setError(errorText(e));
        }
        return false;
      }
    })();

    savePromiseRef.current = run;
    try {
      return await run;
    } finally {
      savePromiseRef.current = null;
    }
  }

  const refresh = useCallback(async () => {
    const current = pageRef.current;
    if (!current) return;
    try {
      const resp = await api.pageDraft(current.id);
      if (!aliveRef.current) return;
      applyPayload(resp);
    } catch (e) {
      if (aliveRef.current) setError(errorText(e));
    }
  }, [applyPayload]);

  const pageKey = page?.id ?? "";

  // SSE：干净的本地状态直接跟进远端；有本地修改时只提示。
  useEffect(() => {
    if (!pageKey) return;
    const source = new EventSource(api.pageDraftStreamUrl(pageKey));
    source.onmessage = (event) => {
      let nextVersion: number | null = null;
      try {
        const data = JSON.parse(event.data) as { version?: unknown };
        nextVersion = typeof data.version === "number" ? data.version : null;
      } catch {
        return;
      }
      if (nextVersion === lastVersionRef.current) return;
      if (
        dirtyRef.current ||
        conflictRef.current ||
        savePromiseRef.current ||
        timerRef.current !== null
      ) {
        pendingRemoteRef.current = nextVersion;
        setRemote(true);
        return;
      }
      lastVersionRef.current = nextVersion;
      void refresh();
    };
    return () => source.close();
  }, [pageKey, refresh]);

  // 切走 / 关页时补一次保存，避免 1.2 秒防抖里的修改丢掉。
  useEffect(() => {
    function flush() {
      const current = pageRef.current;
      if (!current || !dirtyRef.current || conflictRef.current || savePromiseRef.current) {
        return;
      }
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      const built = buildPayload(currentSnapshot());
      if (!built.ok) return;
      void api.savePageDraft(current.id, built.body, true).catch(() => {
        /* 页面已经在离开，失败交给下次打开时提示 */
      });
    }
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, []);

  function markDirty() {
    dirtyRef.current = true;
    editRevRef.current += 1;
    if (!conflictRef.current) setState("dirty");
  }

  function onContentChange(value: string) {
    contentRef.current = value;
    setContent(value);
    markDirty();
    scheduleSave();
  }

  function onBlocksChange(value: string) {
    blocksTextRef.current = value;
    setBlocksText(value);
    markDirty();
    try {
      const blocks = parseBlocks(value);
      setPreviewBlocks(blocks);
      setJsonError("");
      if (!conflictRef.current) setState("dirty");
      scheduleSave();
    } catch (e) {
      setJsonError(`JSON 解析失败：${e instanceof Error ? e.message : String(e)}`);
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (!conflictRef.current) setState("error");
    }
  }

  function changeLayout(value: string) {
    layoutRef.current = value;
    setLayout(value);
    markDirty();
    scheduleSave();
  }

  function changeAccent(value: string) {
    accentRef.current = value;
    setAccent(value);
    markDirty();
    scheduleSave();
  }

  function changeDensity(value: string) {
    densityRef.current = value;
    setDensity(value);
    markDirty();
    scheduleSave();
  }

  async function loadLatest() {
    if (
      (dirtyRef.current || conflictRef.current) &&
      !window.confirm("载入最新草稿会丢失当前未保存的修改，继续？")
    ) {
      return;
    }
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    pendingRemoteRef.current = null;
    setRemote(false);
    setError("");
    await refresh();
  }

  async function discard() {
    const current = pageRef.current;
    if (!current || discarding) return;
    if (!window.confirm("丢弃草稿并恢复为已发布内容？")) return;
    setDiscarding(true);
    if (savePromiseRef.current) await savePromiseRef.current;
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    dirtyRef.current = false;
    conflictRef.current = false;
    try {
      await api.discardPageDraft(current.id);
      const resp = await api.pageDraft(current.id);
      if (aliveRef.current) applyPayload(resp);
    } catch (e) {
      if (aliveRef.current) setError(errorText(e));
    } finally {
      setDiscarding(false);
    }
  }

  async function publish() {
    const current = pageRef.current;
    if (!current || publishing) return;
    setPublishing(true);
    try {
      const saved = await saveNow(true);
      if (!saved) return;
      await api.publishPageDraft(current.id);
      const query = current.subject_id
        ? `?subject=${encodeURIComponent(current.subject_id)}&page=${encodeURIComponent(current.id)}`
        : `?page=${encodeURIComponent(current.id)}`;
      navigate(`/console${query}`);
    } catch (e) {
      setError(conflictText(e));
      setState("error");
    } finally {
      setPublishing(false);
    }
  }

  const previewTheme = useMemo(
    () => themeOf(accent, density, font),
    [accent, density, font],
  );
  const previewPage = useMemo<PageDetail | null>(() => {
    if (!page) return null;
    return {
      ...page,
      body: content,
      blocks: isBlocks ? previewBlocks : null,
      layout,
      theme: previewTheme,
      format: isBlocks ? "blocks" : "markdown",
    };
  }, [page, content, isBlocks, previewBlocks, layout, previewTheme]);

  if (loading) {
    return (
      <div className="page-editor">
        <div className="empty-state">
          <p>正在读取页面…</p>
        </div>
      </div>
    );
  }

  if (!page) {
    return (
      <div className="page-editor">
        <div className="editor-bar">
          <Link className="back-link" to="/console">
            ← 返回阅读
          </Link>
          <h1 className="editor-title">页面不存在</h1>
        </div>
        {error && <div className="editor-error">{error}</div>}
      </div>
    );
  }

  const accentOptions = ACCENTS.some((item) => item.value === accent)
    ? ACCENTS
    : accent && HEX.test(accent)
      ? [...ACCENTS, { value: accent, label: accent }]
      : ACCENTS;

  return (
    <div className="page-editor">
      <header className="editor-bar">
        <Link
          className="back-link"
          to={
            page.subject_id
              ? `/console?subject=${encodeURIComponent(page.subject_id)}&page=${encodeURIComponent(page.id)}`
              : `/console?page=${encodeURIComponent(page.id)}`
          }
        >
          ← 返回阅读
        </Link>
        <h1 className="editor-title">{page.title}</h1>
        <span className={`editor-status is-${state}`}>{STATUS_TEXT[state]}</span>
        <div className="editor-actions">
          <button className="btn btn-ghost" onClick={() => void discard()} disabled={discarding}>
            {discarding ? "丢弃中…" : "丢弃草稿"}
          </button>
          <button className="btn btn-primary" onClick={() => void publish()} disabled={publishing}>
            {publishing ? "发布中…" : "发布"}
          </button>
        </div>
      </header>

      {state === "conflict" && (
        <div className="editor-error">
          <span>有冲突：另一个窗口已修改</span>
          <button className="btn btn-ghost btn-small" onClick={() => void loadLatest()}>
            载入最新草稿
          </button>
        </div>
      )}
      {error && state !== "conflict" && <div className="editor-error">{error}</div>}
      {remote && (
        <div className="editor-remote">
          <span>远端有新版本，当前修改尚未保存</span>
          <button className="btn btn-ghost btn-small" onClick={() => void loadLatest()}>
            载入最新草稿
          </button>
        </div>
      )}

      <div className="page-editor-grid">
        <section className="editor-pane">
          <div className="editor-controls">
            <span className="editor-mode">{isBlocks ? "JSON 块" : "Markdown"}</span>
            <label className="editor-field">
              版式
              <select
                value={layout}
                onChange={(e) => changeLayout(e.target.value)}
                aria-label="版式"
              >
                {LAYOUTS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="editor-field">
              强调色
              <select
                value={accent}
                onChange={(e) => changeAccent(e.target.value)}
                aria-label="强调色"
              >
                <option value="">默认</option>
                {accentOptions.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="editor-field">
              密度
              <select
                value={density}
                onChange={(e) => changeDensity(e.target.value)}
                aria-label="密度"
              >
                <option value="">默认</option>
                {DENSITIES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {isBlocks ? (
            <textarea
              className="editor-textarea is-code"
              value={blocksText}
              onChange={(e) => onBlocksChange(e.target.value)}
              spellCheck={false}
              aria-label="blocks JSON"
            />
          ) : (
            <textarea
              className="editor-textarea"
              value={content}
              onChange={(e) => onContentChange(e.target.value)}
              spellCheck={false}
              aria-label="Markdown 正文"
            />
          )}

          {jsonError && <div className="editor-error editor-error-inline">{jsonError}</div>}
          <div className="editor-foot">
            {isBlocks ? "编辑 blocks 数组；解析失败时保留上一次有效预览。" : "改完 1.2 秒后自动保存草稿。"}
          </div>
        </section>

        <section className="preview-pane">
          <div className="preview-label">
            预览
            {version > 0 && <span className="muted small">草稿 v{version}</span>}
          </div>
          {previewPage && <LessonBody page={previewPage} />}
        </section>
      </div>
    </div>
  );
}
