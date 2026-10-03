# Message editing, versions and reinstatement — owner order of 2 October 2026 (§B, §C, §D)

Built on branch `latency-2026-09-28` at `3dae393`; **NOT INSTALLED** at the time of
writing. Governing text: `04-layer-0.md` §2 amendment of 2 October 2026 (it supersedes
the 12 September "Option 1 — no regeneration" for message edits).

## 1. How the existing structure supports it

The 12 September design already keeps every edit as an appended `message_revisions`
fact numbered under the conversation row lock (`after_sequence`), and reconstructs any
turn as-of its own sequence. That gives versions almost for free:

- **A version** is a revision-kind fact (version 1 is the original wording).
- **A version's continuation** is the set of messages appended while that version was
  in force — in force from its revision's `after_sequence`. So the exchanges that
  followed an earlier wording already *are* that version's continuation; nothing had to
  be re-labelled.
- **One fact was missing**: that he continued from an *earlier* version. Without it,
  every later message would belong to the newest wording. Migration `0033` adds
  `message_version_selections` — append-only, same locking, `revision_number` 0 for the
  original — written in the same transaction as the message he continued with.
- **The view** (`working_thread(..., selections, view)`) shows one version per corrected
  message (the one in force, or the one asked for) and marks every message in another
  version's continuation `in_view = false`: served, kept, not withdrawn, not shown and
  not part of the request's history. The as-of rule applies to selections exactly as to
  revisions, so every earlier call still reconstructs exactly.

## 2. Behaviour

- **Save answers the correction (§B).** `POST /turns` or `/turns/stream` with
  `revise_message_id`: the revision is recorded (the writer's refusals stand — unchanged
  wording, a deliberated message, Restricted content — and then nothing is answered);
  the conversation is read as it now stands (new version in force, old continuation out
  of view); one answer is appended at the end. The message is not re-appended. Cancel
  changes nothing. A title change generates nothing. While Voice is on the request is
  refused with the existing 409 and the desktop keeps the proposed edit open with the
  notice. **An answer still being generated for the earlier wording is not cancelled**:
  it completes into version 1's continuation, so it can never show or play as the answer
  to the corrected request — the typed path has no supersession machinery and none was
  added.
- **Versions (§C).** Each user message with more than one version carries
  `version`, `versions[]` and the desktop shows `‹ 2 of 3 ›`. Viewing an earlier version
  is `GET /conversations/{id}?view=message:number` — a read; nothing recorded or
  generated. Sending while an earlier version is shown sends
  `continue_from_message_id/revision`; the selection is recorded with the message and
  Val is given that version's history. Later exchanges of the other version stay with
  it. Navigating repeats no tool or action.
- **Reinstate (§D).** A withdrawn user message's "Reinstate" sends back the wording in
  force when it was withdrawn (`reinstateWording`); the domain reads a revision that
  returns the withdrawn wording as a reinstatement — `current`, no new version — and the
  answer that followed returns with it. Nothing is generated or re-sent. Show/Hide remain
  inspection only. Reinstating a conversation leaves individual withdrawals as they were
  (different tables, different facts). Nothing here deletes, and nothing is in the way of
  the coming Trash / permanent-deletion design.

## 3. Verification

- Domain (`test_message_versions.py`, 7): a correction starts a version whose
  continuation is what followed; viewing an earlier version shows its own continuation
  and generates nothing; continuing from an earlier version attaches what follows to it;
  the as-of rule applies to selections; a reinstatement with the withdrawn wording is
  not a version; with other wording it is a correction; a version point inside a hidden
  continuation does not hide the view.
- Service (`test_message_versions_service.py`, 3): a saved correction is answered once,
  the request carries the corrected wording and not the earlier answer, the earlier
  answer keeps its version; a refused correction answers nothing; continuing from an
  earlier version uses that version's history and records the selection.
- Earlier tests updated to the new ruling, each annotated: the working-thread as-of
  test, three in `test_message_revisions.py`, the API detail test (now also reads
  `?view=…:1`), and the Tier-1 guard, which reads correction-sensitivity before a
  missing answer (an earlier answer out of view is not a missing answer).
- Schema: migration `0033` round-trips on the test store; the models and the
  transcription agree.
- Desktop: 264 tests (`messageVersions.test.ts` for the continue-from and reinstate
  readings); typecheck and build clean.

## 4. Not done, stated

- No physical check yet. The paths to check in the room: edit → one new answer, cancel,
  `‹ 1 of 2 ›` back and forward with the saved answer shown, continue from the earlier
  version, remove a message and Reinstate it, and an edit while Voice is on.
- An edit of a message that carried attachments answers without re-perceiving them
  (the stored observation is reused by the ordinary rule); not exercised.
