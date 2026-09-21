// What the thread shows for an attachment — Track C.
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

export function Attachments(props: {
  attachments: AttachmentView[] | undefined;
}): React.JSX.Element | null {
  const attachments = props.attachments ?? [];
  if (attachments.length === 0) return null;
  return (
    <div className="attachments">
      {attachments.map((attachment) => (
        <figure key={attachment.id} className="attachment">
          <img
            src={api.attachmentUrl(attachment.sha256)}
            alt={attachment.filename}
            width={attachment.width}
            height={attachment.height}
          />
          <figcaption>
            {attachment.filename}
            {" · "}
            {attachment.width}×{attachment.height}
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
