import { Link } from "react-router-dom";
import type { CardsBlock as CardsBlockData } from "../../types";

/* 卡片网格；站内链接走 <Link>，外部地址退回普通 <a>。 */
export function CardsBlock({ block }: { block: CardsBlockData }) {
  return (
    <div className="block-cards">
      {block.items.map((item, i) => {
        const body = (
          <>
            <div className="block-card-title">{item.title}</div>
            <p className="block-card-text">{item.text}</p>
          </>
        );
        const external = item.link ? /^https?:\/\//i.test(item.link) : false;
        if (!item.link) {
          return (
            <div className="block-card" key={`${item.title}-${i}`}>
              {body}
            </div>
          );
        }
        return external ? (
          <a
            className="block-card is-link"
            key={`${item.title}-${i}`}
            href={item.link}
            target="_blank"
            rel="noreferrer"
          >
            {body}
          </a>
        ) : (
          <Link className="block-card is-link" key={`${item.title}-${i}`} to={item.link}>
            {body}
          </Link>
        );
      })}
    </div>
  );
}
