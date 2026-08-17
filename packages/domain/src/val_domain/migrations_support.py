"""SQL that more than one migration needs, defined once.

A migration is normally self-contained — it is a record of one change and reads
best when everything it does is in front of you. This module exists for the one
case where that breaks down: a **view definition that a later migration must
recreate**.

`model_calls_accounted` is defined with `mc.*`, which expands to the columns that
existed when the view was created. Every migration that adds a column to
`model_calls` must therefore drop and recreate it, or the view quietly stops
exposing the new column and becomes a second, lesser record of the same table.

Copying the definition into each migration would work until the two copies
disagreed, and the disagreement would show up as a view that was correct at one
revision and wrong at the next. One definition, imported. Changing it is a new
migration that recreates the view, never an edit that silently changes what an
old migration did.
"""

#: `model_calls`, read through the rule that supersedes the fabricated zeroes of
#: 15 August 2026. Full reasoning: migration `0004_supersede_zero_costs`.
ACCOUNTED_VIEW = """
CREATE VIEW model_calls_accounted AS
SELECT
    mc.*,
    CASE
        WHEN mc.cost_certainty IS NOT NULL THEN mc.cost_certainty
        -- Written before 17 August 2026. The implementation of the day wrote
        -- 0/0/$0 on every error and real usage on everything else, so this
        -- reads the record rather than guessing at it.
        WHEN mc.status = 'error' THEN 'unknown'::model_call_cost_certainty
        ELSE 'known'::model_call_cost_certainty
    END AS effective_cost_certainty,
    CASE
        WHEN mc.cost_certainty = 'unknown' THEN NULL
        WHEN mc.cost_certainty IS NULL AND mc.status = 'error' THEN NULL
        ELSE mc.cost
    END AS accounted_cost,
    CASE
        WHEN mc.cost_certainty IS NULL AND mc.status = 'error' THEN
            'Superseded accounting semantics. This row was written before '
            '17 August 2026, when a failed call recorded zero tokens and zero '
            'cost regardless of whether the provider had been reached. The '
            'stored 0.000000 is not a confirmed cost: the true cost is unknown '
            'and is at least the input tokens the provider consumed. The '
            'original row is preserved unmodified; see migration '
            '0004_supersede_zero_costs.'
        ELSE NULL
    END AS accounting_note
FROM model_calls mc
"""
