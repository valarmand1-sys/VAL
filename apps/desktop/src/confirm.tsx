// Asking him before an act that needs his word — inside the window.
//
// Owner's physical check, 2 October 2026: "Remove does nothing." Every confirmation in
// this app was `window.confirm`, and the desktop shell's webview shows no dialog for it:
// the call returns false at once, so the act was silently declined every time — Remove
// on a conversation, Remove on a message, Move, and the question asked before a
// conversation change ends Voice. The question is now asked in the window itself.
//
// One question at a time; a second ask while one is open is declined rather than
// stacked. Nothing is done unless he presses the confirming button.

import { useEffect, useState } from "react";

interface Pending {
  question: string;
  confirmLabel: string;
  settle: (answer: boolean) => void;
}

let present: ((pending: Pending | null) => void) | null = null;
let open: Pending | null = null;

/** Ask, and resolve with his answer. False when no host is mounted or one is open. */
export function askToConfirm(question: string, confirmLabel = "Continue"): Promise<boolean> {
  if (present === null || open !== null) return Promise.resolve(false);
  return new Promise((resolve) => {
    open = {
      question,
      confirmLabel,
      settle: (answer) => {
        open = null;
        present?.(null);
        resolve(answer);
      },
    };
    present?.(open);
  });
}

/** Mounted once, in the app shell. */
export function ConfirmHost(): React.JSX.Element | null {
  const [pending, setPending] = useState<Pending | null>(null);
  useEffect(() => {
    present = setPending;
    return () => {
      present = null;
      open?.settle(false);
    };
  }, []);
  if (pending === null) return null;
  return (
    <div className="confirm-backdrop" role="presentation">
      <div className="confirm" role="alertdialog" aria-modal="true" aria-label="Confirm">
        <p>{pending.question}</p>
        <div className="confirm-actions">
          <button autoFocus onClick={() => pending.settle(false)}>
            Cancel
          </button>
          <button className="confirm-yes" onClick={() => pending.settle(true)}>
            {pending.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
