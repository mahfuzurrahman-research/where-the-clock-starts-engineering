# Process Anomaly Detection and Review

## Historical reference and later scoring

The baseline is fitted from valid COMPLETE cases as known at the earlier recorded-arrival cutoff, including only cases registered by that cutoff. Open, empty and review cases are excluded. Later arrivals and backdated corrections delivered after the cutoff cannot change this frozen reference. The source hash recorded with it includes only records known by then.

For each declared service group, the detector calculates a median and median absolute deviation of `log1p(notification_to_decision_hours)`. Each group needs at least 12 eligible historical cases in the default policy; inadequate support fails rather than selecting an implicit fallback. The default fixture supplies 30 per group.

For a later complete case with duration $d$ in group $g$:

$$s = \frac{\log(1+d)-m_g}{\max(1.4826\,MAD_g,\;0.1)}.$$

Only cases outside the fitted training-case set are scored. A duration candidate requires **both** `s > 3.5` and `d > 72 hours`. Equality does not trigger. The floor handles a zero-MAD historical group. These transformations, constants and thresholds are declared engineering choices, not a calibrated false-positive rate or a legal standard. The detector is an upper-tail reference deviation rule, not a causal model.

## Review reasons

| Category / priority | Reasons and evidence |
|---|---|
| Data quality / P1 | No observed events, missing predecessors, ambiguous live stages or stage reversal; current state and available timestamps |
| Process pattern / P2 | A withdrawn decision; open notification age above 72 hours; waiting for notification above 96 issue-age hours |
| Duration candidate / P2 | Upper-tail duration deviation and absolute floor; duration, score, thresholds, cutoff and baseline hash |
| Delivery quality / P3 | Duplicate delivery/version, stale revision, late update, accepted revision above one; delivery/revision evidence |

Priorities are declared routing categories and do not measure legal severity. A case can have several rule-level rows. IDs are stable for a case/reason pair. Every row is `review_required`, synthetic, and explicitly sets legal-breach and wrongdoing claims to false.

An old delivery anomaly remains in the historical audit even when a later correction repairs the current process clock. A newly registered case without observed events indicates source absence; it does not establish that the actual process failed. Repeated stages may be legitimate outside this toy path.

## Evaluation and boundaries

The generator includes 12 named fabricated scenarios for expected state/rule assertions. Labels never fit the reference or select thresholds. These scenarios test intended software behavior; they are not an external evaluation sample and do not support sensitivity, specificity, fairness, calibration or production-performance claims.

The default snapshot produces 18 rule-level review rows across 11 cases. Of 42 later valid completed cases, one meets the duration rule. These are illustrative fixture outputs, not empirical findings or a detector-accuracy estimate.

SQLite independently reconstructs both snapshots from raw records, chooses historical membership, calculates group medians/MADs, and compares scores and queue coverage. It shares only the scalar `math.log1p` callback with Python. Verification receipts reconstruct replay, reference, and review results from saved raw inputs; they do not authenticate the source.

[NIST's outlier-detection discussion](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm) provides context for median/MAD-based diagnostics. This repository's grouped log-duration rule, floor and threshold combination remain an explicitly declared synthetic protocol.
