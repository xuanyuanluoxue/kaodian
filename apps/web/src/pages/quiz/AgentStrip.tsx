import { useState } from "react";

/* 顶部 Agent 条 + 「卡住了」求助框。 */

interface Props {
  note?: string;
  /** 返回 true 表示已发送；失败时由外层负责提示错误。 */
  onSend: (text: string) => Promise<boolean>;
}

export function AgentStrip({ note, onSend }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function send() {
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      if (await onSend(text)) {
        setSent(true);
        setText("");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="agent-strip">
        <span className="agent-badge">Agent</span>
        <p>{note || "在对话里让 Agent 出题；需要提示就点右边的「卡住了」。"}</p>
        <button
          className="btn btn-ghost agent-help-btn"
          onClick={() => {
            setOpen((v) => !v);
            setSent(false);
          }}
        >
          {open ? "收起" : "卡住了"}
        </button>
      </div>
      {open && (
        <div className="help-box">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="哪一步卡住了？Agent 会看到题目编号、本题用时和你的描述。"
            rows={3}
            aria-label="卡在哪里"
          />
          <div className="help-actions">
            <span className="muted small">
              {sent ? "已发送，Agent 会在对话里看到。" : "不会自动重试，发送后继续答下一题即可。"}
            </span>
            <button className="btn btn-primary" onClick={send} disabled={!text.trim() || sent || busy}>
              {busy ? "发送中…" : sent ? "已发送" : "发送给 Agent"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
