import type { QuestionMedia as Media } from "../types";

/* 题目 / 材料引用的图、音频、视频。空数组不占位。 */

interface Props {
  media?: Media[] | null;
}

function sourceLabel(item: Media): string {
  const parts: string[] = [];
  if (item.source) parts.push(`来源：${item.source}`);
  if (item.license) parts.push(`许可：${item.license}`);
  return parts.join(" · ");
}

export function QuestionMedia({ media }: Props) {
  if (!media || media.length === 0) return null;

  return (
    <div className="question-media">
      {media.map((item, i) => {
        const meta = sourceLabel(item);
        return (
          <figure className={`question-media-item is-${item.type}`} key={`${item.url}-${i}`}>
            {item.type === "image" && (
              <img src={item.url} alt={item.alt || ""} loading="lazy" decoding="async" />
            )}
            {item.type === "audio" && (
              <audio
                controls
                preload="none"
                src={item.url}
                aria-label={item.alt || "材料音频"}
              />
            )}
            {item.type === "video" && (
              <video
                controls
                preload="metadata"
                src={item.url}
                aria-label={item.alt || "材料视频"}
              />
            )}
            {item.type === "image" && item.alt ? (
              <figcaption>{item.alt}</figcaption>
            ) : null}
            {meta ? <p className="question-media-meta">{meta}</p> : null}
          </figure>
        );
      })}
    </div>
  );
}
