import { Markdown } from "./Markdown";
import { QuestionMedia } from "./QuestionMedia";
import type { QuestionGroup } from "../types";

/* 材料题共用的材料卡片：Markdown 正文（公式 / 图 / 表格）+ 媒体。
   答题页默认展开；结果页用 collapsible 收起长文。 */

interface Props {
  group?: QuestionGroup | null;
  /** 结果页用：默认收起，点击标题展开。 */
  collapsible?: boolean;
}

export function GroupMaterial({ group, collapsible = false }: Props) {
  if (!group) return null;

  const title = group.title?.trim() || "材料";
  const count = group.question_ids?.length || 0;
  const body = (
    <div className="group-material-body">
      {group.material?.trim() ? <Markdown>{group.material}</Markdown> : null}
      <QuestionMedia media={group.media} />
    </div>
  );

  if (collapsible) {
    return (
      <details className="group-material is-collapsible">
        <summary>
          <span className="group-material-title">{title}</span>
          {count > 0 && <span className="muted small">本材料 {count} 道小题</span>}
        </summary>
        {body}
      </details>
    );
  }

  return (
    <section className="group-material" aria-label={title}>
      <div className="group-material-head">
        <span className="group-material-kicker">材料</span>
        <h3 className="group-material-title">{title}</h3>
        {count > 1 && <span className="muted small">{count} 道小题共用</span>}
      </div>
      {body}
    </section>
  );
}
