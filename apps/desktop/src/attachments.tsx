// What the thread shows for an attachment — Track C, extended to video and
// audio by the owner's execution order of 22 September 2026.
//
// This lives in its own module for one reason: **the test renders this exact
// component.** Owner correction, 20 September 2026 — the earlier regression test
// defined its own copy of this markup, so it could have gone on passing while
// the shipped thread diverged or broke. That is the same failure as asserting a
// URL string: it proves the test's own copy works, not the shipped code.
//
// The element is deliberately plain. The `src` is a pure function of the content
// digest, so a conversation reopened months later resolves exactly the bytes
// that were stored: no session, no signed link, no expiry. The dimensions are
// the attachment's true ones, and the classification is shown as stated rather
// than inferred, because what the house was told about a file is part of what
// the file is.

import type { AttachmentView } from "./api";
import { api } from "./api";

// Seconds as a clock reading. A recording's length is a fact the owner reads at
// a glance, and "134.2" is not that.
export function runtimeOf(seconds: number | null): string | null {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return null;
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

// The medium itself, rendered as what it is. Controls on the time-based media
// because an attachment the owner cannot play is an attachment he has to take
// on trust — and the source is the same content-addressed URL in all three
// cases, so nothing here needs a session or an expiry.
function Medium(props: { attachment: AttachmentView }): React.JSX.Element {
  const { attachment } = props;
  const src = api.attachmentUrl(attachment.sha256);
  if (attachment.modality === "video") {
    return <video src={src} controls preload="metadata" />;
  }
  if (attachment.modality === "audio") {
    return <audio src={src} controls preload="metadata" />;
  }
  return (
    <img
      src={src}
      alt={attachment.filename}
      width={attachment.width}
      height={attachment.height}
    />
  );
}

export function Attachments(props: {
  attachments: AttachmentView[] | undefined;
}): React.JSX.Element | null {
  const attachments = props.attachments ?? [];
  if (attachments.length === 0) return null;
  return (
    <div className="attachments">
      {attachments.map((attachment) => (
        <figure
          key={attachment.id}
          className={`attachment attachment-${attachment.modality}`}
        >
          <Medium attachment={attachment} />
          <figcaption>
            {attachment.filename}
            {" · "}
            {/* An image says its dimensions; a recording says its length.
                Saying the wrong one of the two is how a caption stops being
                information and becomes decoration. */}
            {attachment.modality === "audio"
              ? (runtimeOf(attachment.duration_seconds) ?? "audio")
              : `${attachment.width}×${attachment.height}`}
            {attachment.modality === "video" &&
              runtimeOf(attachment.duration_seconds) !== null &&
              ` · ${runtimeOf(attachment.duration_seconds)}`}
            {" · "}
            <span className={`class-${attachment.classification}`}>
              {attachment.classification}
            </span>
          </figcaption>
        </figure>
      ))}
    </div>
  );
}
