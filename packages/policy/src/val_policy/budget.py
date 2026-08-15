"""The Layer 0 hard stop (`01-architecture.md` §5.7).

One crude guard, deliberately: if month-to-date cloud spend has reached the
ceiling, cloud routing stops. The graduated thresholds, the reserve, and the
cost dashboard arrive at Layer 3, when Roles multiply call volume and the gap
between fine and breached can be crossed inside a single task.

Pure arithmetic. The gateway supplies the month-to-date figure from
`model_calls`; enforcement happens **before** the call is made
(`00-charter.md` invariant 24), never reported after.
"""

#: The routing ceiling: cloud model inference, per month (01-architecture.md §5.5).
CLOUD_CEILING_USD = 200.00


def cloud_call_permitted(month_to_date_spend_usd: float) -> bool:
    """Whether one more cloud call may be made this month."""
    return month_to_date_spend_usd < CLOUD_CEILING_USD


def ceiling_message(month_to_date_spend_usd: float) -> str:
    """What Val says, plainly, when the ceiling has stopped cloud routing."""
    return (
        f"Cloud routing has stopped: month-to-date cloud spend is "
        f"${month_to_date_spend_usd:.2f} against the ${CLOUD_CEILING_USD:.2f} "
        "ceiling. It resets at the start of next month. I cannot degrade to "
        "local inference until Layer 1, so cloud-model work waits "
        "(01-architecture.md §5.6, §5.7)."
    )
