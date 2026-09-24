"""Small, dependency-free statistics: Wilson intervals and the audit-corrected estimate."""

from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((centre - half) / denom, (centre + half) / denom)


def corrected_count(
    flagged: int, unflagged: int,
    audit_pos_yes: int, audit_pos_n: int,
    audit_neg_yes: int, audit_neg_n: int,
) -> dict:
    """Estimate true corrections from a stratified audit.

    The audit samples separately from messages the model flagged and messages it
    did not. Precision comes from the flagged sample, the miss rate from the
    unflagged one, and each is scaled back to its stratum's size:

        true ~= flagged * precision + unflagged * miss_rate
    """
    precision = audit_pos_yes / audit_pos_n if audit_pos_n else None
    miss = audit_neg_yes / audit_neg_n if audit_neg_n else None
    if precision is None or miss is None:
        return {"precision": precision, "miss_rate": miss, "estimate": None, "low": None, "high": None}
    p_lo, p_hi = wilson(audit_pos_yes, audit_pos_n)
    m_lo, m_hi = wilson(audit_neg_yes, audit_neg_n)
    est = flagged * precision + unflagged * miss
    # Conservative bounds: combine the interval ends of both strata.
    return {
        "precision": precision,
        "miss_rate": miss,
        "estimate": est,
        "low": flagged * p_lo + unflagged * m_lo,
        "high": flagged * p_hi + unflagged * m_hi,
    }
