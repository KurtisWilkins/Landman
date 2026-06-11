"""Underwriting domain (design doc §5.5): the pro forma engine — 5-year levered cash flow,
return metrics (IRR, equity multiple, going-in cap, Yr-1 cash-on-cash), the NOI bridge, the
3-hurdle equity waterfall, and hurdle pass/fail.

The math here is correctness-critical and pure (Decimal money/rates, never float). Default
hurdle thresholds, waterfall structure (catch-up / return-of-capital), and financing terms
are unresolved decisions (§14 A-1..A-4) and are supplied as inputs read from config — never
hard-coded here.
"""
