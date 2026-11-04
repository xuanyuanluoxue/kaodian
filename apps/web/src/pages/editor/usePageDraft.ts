import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api";
import { errorText } from "../../lib/format";
import type { Block, BlockType, PageDetail, PageDraftResponse } from "../../types";
import { defaultBlock } from "./blockDefaults";
import {
  buildPayload,
  conflictText,
  parseBlocks,
  type EditorSnapshot,
} from "./draft";

/* 草稿生命周期 + 块编辑状态：加载、防抖保存、SSE、发布都收在这里。 */

export type SaveState = "saved" | "dirty" | "saving" | "conflict" | "error";
export type BlocksMode = "visual" | "json";

export const STATUS_TEXT: Record<SaveState, string> = {
  saved: "已保存",
  dirty: "未保存",
  saving: "保存中…",
  conflict: "有冲突",
  error: "保存失败",
};

export function usePageDraft(pageId: string) {
  const navigate = useNavigate();

  const [page, setPage] = useState<PageDetail | null>(null);
  const [content, setContent] = useState("");
  const [blocksText, setBlocksText] = useState("[]");
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [blocksMode, setBlocksMode] = useState<BlocksMode>("visual");
  const [selected, setSelected] = useState(-1);
  const [pickerOpen, setPickerOpen] = useState(false);
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
    const rawBlocks = draft ? draft.blocks : (nextPage.blocks ?? null);
    const nextBlocks = rawBlocks ?? [];
    const nextBlocksText = JSON.stringify(nextBlocks, null, 2);
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
    setBlocks(nextBlocks);
    setSelected((prev) => (prev >= 0 && prev < nextBlocks.length ? prev : -1));
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
      const parsed = parseBlocks(value);
      setBlocks(parsed);
      setSelected((prev) => (prev >= 0 && prev < parsed.length ? prev : -1));
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

  /** 可视化编辑统一出口：同步 blocks、JSON 文本、选中项、防抖保存。 */
  function updateBlocks(next: Block[], nextSelected: number) {
    const text = JSON.stringify(next, null, 2);
    blocksTextRef.current = text;
    setBlocksText(text);
    setBlocks(next);
    setSelected(next.length ? Math.min(Math.max(nextSelected, 0), next.length - 1) : -1);
    setJsonError("");
    markDirty();
    scheduleSave();
  }

  function changeBlocksMode(next: BlocksMode) {
    if (next === blocksMode) return;
    if (next === "visual") {
      try {
        const parsed = parseBlocks(blocksTextRef.current);
        setBlocks(parsed);
        setSelected((prev) => (prev >= 0 && prev < parsed.length ? prev : -1));
        setJsonError("");
        if (state === "error" && jsonError && !conflictRef.current) {
          setState(dirtyRef.current ? "dirty" : "saved");
        }
      } catch (e) {
        setJsonError(`JSON 解析失败：${e instanceof Error ? e.message : String(e)}`);
        if (!conflictRef.current) setState("error");
        return;
      }
    }
    setBlocksMode(next);
  }

  function addBlock(type: BlockType) {
    const at = selected >= 0 && selected < blocks.length ? selected + 1 : blocks.length;
    const next = [...blocks.slice(0, at), defaultBlock(type), ...blocks.slice(at)];
    updateBlocks(next, at);
    setPickerOpen(false);
  }

  function moveBlock(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= blocks.length) return;
    const next = [...blocks];
    [next[index], next[target]] = [next[target], next[index]];
    updateBlocks(next, target);
  }

  function duplicateBlock(index: number) {
    if (index < 0 || index >= blocks.length) return;
    const copy = JSON.parse(JSON.stringify(blocks[index])) as Block;
    const next = [...blocks.slice(0, index + 1), copy, ...blocks.slice(index + 1)];
    updateBlocks(next, index + 1);
  }

  function deleteBlock(index: number) {
    if (index < 0 || index >= blocks.length) return;
    const next = blocks.filter((_, i) => i !== index);
    updateBlocks(next, next.length ? Math.min(index, next.length - 1) : -1);
  }

  function changeBlock(index: number, block: Block) {
    if (index < 0 || index >= blocks.length) return;
    const next = [...blocks];
    next[index] = block;
    updateBlocks(next, index);
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

  return {
    page,
    content,
    blocks,
    blocksText,
    blocksMode,
    selected,
    pickerOpen,
    layout,
    accent,
    density,
    font,
    version,
    state,
    error,
    jsonError,
    remote,
    loading,
    publishing,
    discarding,
    setSelected,
    setPickerOpen,
    onContentChange,
    onBlocksChange,
    changeBlocksMode,
    addBlock,
    moveBlock,
    duplicateBlock,
    deleteBlock,
    changeBlock,
    changeLayout,
    changeAccent,
    changeDensity,
    loadLatest,
    discard,
    publish,
  };
}
