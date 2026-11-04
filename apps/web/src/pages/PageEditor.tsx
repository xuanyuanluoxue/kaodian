import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { LessonBody } from "../components/blocks/LessonBody";
import type { PageDetail } from "../types";
import { BlockForm } from "./editor/BlockForm";
import { BlockList, BlockPicker } from "./editor/BlockList";
import { BLOCK_LABELS } from "./editor/blockDefaults";
import { themeOf } from "./editor/draft";
import { STATUS_TEXT, usePageDraft } from "./editor/usePageDraft";

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

export function PageEditor() {
  const { pageId = "" } = useParams();
  const editor = usePageDraft(pageId);
  const {
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
  } = editor;

  const isBlocks =
    page?.format === "blocks" || (page?.format == null && Array.isArray(page?.blocks));

  const previewTheme = useMemo(
    () => themeOf(accent, density, font),
    [accent, density, font],
  );
  const previewPage = useMemo<PageDetail | null>(() => {
    if (!page) return null;
    return {
      ...page,
      body: content,
      blocks: isBlocks ? blocks : null,
      layout,
      theme: previewTheme,
      format: isBlocks ? "blocks" : "markdown",
    };
  }, [page, content, isBlocks, blocks, layout, previewTheme]);

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

  const selectedBlock = selected >= 0 ? blocks[selected] : undefined;

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
          {isBlocks && (
            <div className="editor-mode-switch" role="tablist" aria-label="块编辑模式">
              <button
                type="button"
                role="tab"
                aria-selected={blocksMode === "visual"}
                className={blocksMode === "visual" ? "is-active" : undefined}
                onClick={() => changeBlocksMode("visual")}
              >
                可视化
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={blocksMode === "json"}
                className={blocksMode === "json" ? "is-active" : undefined}
                onClick={() => changeBlocksMode("json")}
              >
                JSON
              </button>
            </div>
          )}

          <div className="editor-controls">
            <span className="editor-mode">{isBlocks ? "块页" : "Markdown"}</span>
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
            blocksMode === "visual" ? (
              <div className="block-editor">
                <div className="block-editor-toolbar">
                  <button
                    type="button"
                    className="btn btn-ghost btn-small"
                    onClick={() => setPickerOpen((open) => !open)}
                  >
                    ＋ 添加块
                  </button>
                  <span className="muted small">{blocks.length} 个块</span>
                </div>
                {pickerOpen && (
                  <BlockPicker onAdd={addBlock} onClose={() => setPickerOpen(false)} />
                )}
                <BlockList
                  blocks={blocks}
                  selected={selected}
                  onSelect={setSelected}
                  onMove={moveBlock}
                  onDuplicate={duplicateBlock}
                  onDelete={deleteBlock}
                  onAdd={() => setPickerOpen(true)}
                />
                {selectedBlock && (
                  <div className="block-form-panel">
                    <div className="block-form-head">
                      编辑第 {selected + 1} 个块 · {BLOCK_LABELS[selectedBlock.type]}
                    </div>
                    <BlockForm
                      key={selected}
                      block={selectedBlock}
                      onChange={(block) => changeBlock(selected, block)}
                    />
                  </div>
                )}
              </div>
            ) : (
              <textarea
                className="editor-textarea is-code"
                value={blocksText}
                onChange={(e) => onBlocksChange(e.target.value)}
                spellCheck={false}
                aria-label="blocks JSON"
              />
            )
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
            {isBlocks
              ? blocksMode === "visual"
                ? "选中块后编辑表单；修改 1.2 秒后自动保存草稿。"
                : "编辑 blocks 数组；解析失败时保留上一次有效预览，且不能切回可视化。"
              : "改完 1.2 秒后自动保存草稿。"}
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
