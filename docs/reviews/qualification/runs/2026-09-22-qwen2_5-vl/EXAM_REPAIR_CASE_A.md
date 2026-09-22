# Case A — exam repair amendment

**Ruled by Lord Armand, 22 September 2026.** Recorded here before Qwen2.5-VL ran,
as an explicit amendment and not a silent replacement.

## The original criterion, verbatim

From `FROZEN_ACCEPTANCE_TEST.md`, committed in `0d41337` before any candidate
was loaded:

> **Passes only if all four central facts are established:**
>
> 1. three people are present;
> 2. **the child/boy is dressed as a magician, including the top hat;**
> 3. the people are embracing/hugging;
> 4. they are indoors, in a living-room or home environment.

with the matching fail condition:

> **Fails if it** materially miscounts the people, **misses the magician
> identity/costume**, materially misstates the central action, materially
> misstates the setting, or invents a central person, object or action that is
> not present.

## The defect, demonstrable without any candidate's answer

The frozen prompt — unchanged, and quoted here in full because the repair turns
on it — says:

> Report only what you can actually see in this image. Do not guess, do not
> interpret motives, and do not add anything that is not visible. Cover: how
> many people are present; what the child is wearing; what the people are doing;
> the setting; and any major visible continuity details.

"Magician" is not a visible thing. A top hat is visible; a cape is visible; the
inference from those to *a child dressed as a magician* is an interpretation, and
the prompt forbids interpretation in three separate clauses. **The paper
contradicts itself**: it instructs a candidate not to interpret and then requires
an interpretation to pass. That is legible from the two texts side by side, with
no answer in front of you, which is what the standing exam-repair rule requires.

## The repaired criterion

Minimal: the interpretive identity label is replaced by the directly visible
clothing elements that supported it. Nothing else in the case changes.

> **Passes only if the result establishes:**
>
> 1. three people are present;
> 2. **the child wears a top hat and a cape;**
> 3. the people are embracing/hugging;
> 4. the setting is an indoor living-room or home environment;
> 5. no material central person, object or action is invented.

The literal word "magician" is **not** required.

Colour, lining, material and style labels are **not** pass criteria. They were
never in the frozen criteria, and they are deliberately excluded so that nothing
is back-filled from what earlier candidates happened to say.

## The prompt is unchanged

The frozen Case A prompt is used exactly as committed. This candidate sits the
same question the two earlier candidates sat. Only the marking changes.

## Effect on the earlier results

Recorded for completeness; **neither earlier candidate is reopened and neither
overall result changes.**

- **MiniCPM-o 4.5** reported "a black top hat and a black coat (with a hint of
  red lining at the bottom)". Under the repaired criterion its Case A reads
  differently: it names the top hat, but calls the garment a coat rather than a
  cape, so the cape element is not clearly established. Under the original
  criterion it was recorded as a flagged pass.
- **Qwen3-Omni** reported "a black top hat and a black cape with a red inner
  lining". Under the repaired criterion its Case A is a clean pass on all five
  points, where it was previously recorded as a flagged pass.

**Both candidates remain closed on their own account, because each failed Case C**
— MiniCPM-o lost the sequence that its runtime never delivered, and Qwen3-Omni
lost a sequence that was delivered intact. Case A was never what closed either
of them, so the repair moves nothing.

The flag raised on both earlier runs — that the costume was described accurately
while the label was absent, possibly because the prompt forbade inferring it —
is what this amendment resolves.
