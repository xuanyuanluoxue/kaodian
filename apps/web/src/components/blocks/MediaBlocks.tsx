import type {
  AudioBlock as AudioBlockData,
  ImageBlock as ImageBlockData,
  VideoBlock as VideoBlockData,
} from "../../types";

/* 讲义里的图 / 视频 / 音频：原生控件，只接受后端已校验的地址。 */
export function ImageBlock({ block }: { block: ImageBlockData }) {
  return (
    <figure className="block-image">
      <img src={block.url} alt={block.alt || block.caption || ""} loading="lazy" decoding="async" />
      {block.caption || block.license ? (
        <figcaption>
          {block.caption ? <span>{block.caption}</span> : null}
          {block.license ? (
            <span className="block-image-license">许可：{block.license}</span>
          ) : null}
        </figcaption>
      ) : null}
    </figure>
  );
}

export function VideoBlock({ block }: { block: VideoBlockData }) {
  return (
    <figure className="block-video">
      <video
        controls
        preload="metadata"
        src={block.url}
        poster={block.poster}
        aria-label="讲义视频"
      />
    </figure>
  );
}

export function AudioBlock({ block }: { block: AudioBlockData }) {
  return (
    <figure className="block-audio">
      <audio controls preload="none" src={block.url} aria-label={block.title || "讲义音频"} />
      {block.title ? <figcaption className="block-media-title">{block.title}</figcaption> : null}
    </figure>
  );
}
