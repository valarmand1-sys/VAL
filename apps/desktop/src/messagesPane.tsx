// The conversation's scrolling region, and where it stays — owner's physical check,
// 2 October 2026: once a conversation was long enough to scroll, every send and every
// answer returned the view to the top.
//
// Two causes, both here. Nothing ever followed new content: the newest exchange arrived
// below the fold. And the region is rendered by two components — the settled thread and
// the thread while a typed turn streams — so each send replaced the scrolling element
// with a new one, which starts at the top.
//
// The rule: **follow the newest exchange unless he has scrolled up to read.** While he
// is at (or near) the bottom, new content keeps the bottom in view. Once he scrolls up,
// his position is his: nothing moves it — not an update, and not the element being
// replaced — until he returns to the bottom himself or opens another conversation.

import { useLayoutEffect, useRef } from "react";

export interface ScrollMemory {
  /** True while the view follows the newest content. */
  following: boolean;
  /** Where he left the view, when he is not following. */
  top: number;
  /** The conversation this memory is about; another conversation starts following. */
  conversation: string | null;
}

export function newScrollMemory(): ScrollMemory {
  return { following: true, top: 0, conversation: null };
}

/** How close to the bottom still counts as "at the bottom", in pixels. */
export const FOLLOW_WITHIN_PX = 48;

export function MessagesPane(props: {
  memory: ScrollMemory;
  conversation: string | null;
  children: React.ReactNode;
}): React.JSX.Element {
  const { memory, conversation } = props;
  const element = useRef<HTMLDivElement | null>(null);
  const mounted = useRef(false);

  // After every render: content may have grown, or this may be a new element.
  useLayoutEffect(() => {
    const pane = element.current;
    if (pane === null) return;
    if (memory.conversation !== conversation) {
      memory.conversation = conversation;
      memory.following = true;
    }
    if (memory.following) {
      pane.scrollTop = pane.scrollHeight;
    } else if (!mounted.current) {
      // A replaced element starts at the top; put him back where he was reading.
      pane.scrollTop = memory.top;
    }
    mounted.current = true;
  });

  return (
    <div
      className="messages"
      ref={element}
      onScroll={(event) => {
        const pane = event.currentTarget;
        memory.top = pane.scrollTop;
        memory.following =
          pane.scrollHeight - pane.scrollTop - pane.clientHeight <= FOLLOW_WITHIN_PX;
      }}
    >
      {props.children}
    </div>
  );
}
