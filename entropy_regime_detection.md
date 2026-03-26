# Trading Bot v2 — Dev Analysis & Improvement Proposal

## 1. How the Bot Classifies Regime — Transition Detection

P(n) = exp(−|ΔH/H|),  ΔP = P(n) − P(n−1)

A transition is detected when ΔP falls inside the band centered on the structural value (see **Section 8**):

```
ΔP ∈ [−0.34 − tol, −0.34 + tol]  →  neutral→bull
ΔP ∈ [−0.86 − tol, −0.86 + tol]  →  neutral→bear
ΔP ∈ [−0.15 − tol, −0.15 + tol]  →  bull→neutral
ΔP ∈ [+0.37 − tol, +0.37 + tol]  →  bear→neutral
ΔP ∈ [−tol,        +tol]          →  neutral→neutral

tol = 0.025  (tunable parameter)
```

The transition name determines the bot action — not a one-sided threshold.

---

## 2. ΔP Signature Matrix (9×9)

Rows = previous transition, columns = current transition, cell = ΔP = P(current) − P(previous).
Forbidden cells (— ) are transitions where the "to" regime of the previous does not match the "from" regime of the current — physically impossible sequences.

| prev \ cur | n→neutral | n→bull | n→bear | bull→n | bull→bull | bull→bear | bear→n | bear→bull | bear→bear |
|:-----------|:---------:|:------:|:------:|:------:|:---------:|:---------:|:------:|:---------:|:---------:|
| **n→neutral**   |  0.00 | −0.34 | −0.86 | —     | —         | —         | —      | —         | —         |
| **n→bull**      | —     | —     | —     | −0.15 |  0.00     | −0.52     | —      | —         | —         |
| **n→bear**      | —     | —     | —     | —     | —         | —         | +0.37  | +0.52     |  0.00     |
| **bull→neutral**| +0.49 | +0.15 | −0.37 | —     | —         | —         | —      | —         | —         |
| **bull→bull**   | —     | —     | —     | −0.15 |  0.00     | −0.52     | —      | —         | —         |
| **bull→bear**   | —     | —     | —     | —     | —         | —         | +0.37  | +0.52     |  0.00     |
| **bear→neutral**| +0.49 | +0.15 | −0.37 | —     | —         | —         | —      | —         | —         |
| **bear→bull**   | —     | —     | —     | −0.15 |  0.00     | −0.52     | —      | —         | —         |
| **bear→bear**   | —     | —     | —     | —     | —         | —         | +0.37  | +0.52     |  0.00     |

Each row has exactly 3 valid cells. Key observations:
- Rows ending in the same regime share identical ΔP patterns
- `n→bear → bear→neutral`: +0.37 — the ΔP_pair for bear (P snaps back)
- `n→bull → bull→neutral`: −0.15 — the ΔP_pair for bull (P drifts lower)
- `n→bull → bull→bear`:    −0.52 — direct jump signature, distinct from `n→neutral → n→bear` (−0.86)

---

## 3. ΔP per State Machine Event

Each state machine event corresponds to a specific cell in the 9×9 matrix — defined by the previous transition AND the detected transition.

| Previous transition | Transition detected | ΔP used |
|:--------------------|:--------------------|:-------:|
| neutral→neutral     | neutral→bull        | −0.34   |
| neutral→bull        | bull→neutral        | −0.15   |
| neutral→neutral     | neutral→bear        | −0.86   |
| neutral→bear        | bear→neutral        | +0.37   |
| bull→neutral        | neutral→bull        | +0.15   |
| bear→neutral        | neutral→bear        | −0.37   |

Key insight: **the same transition can have different ΔP depending on context**.
`neutral→bull` has ΔP = −0.34 after neutral→neutral (OPEN LONG) but ΔP = +0.15 after bull→neutral (CYCLE REPEAT). The ΔP band detection in section 1 distinguishes these two cases.

---

## 4. Market Confirmation of State Machine Pairs

Empirical verification of each (previous transition, current transition) pair against live data:

| # | Previous transition | Current transition | Status |
|---|--------------------|--------------------|--------|
| 1 | neutral→neutral    | neutral→bull       | ✅ confirmed |
| 2 | neutral→bull       | bull→neutral       | ✅ confirmed |
| 3 | neutral→neutral    | neutral→bear       | ✅ confirmed |
| 4 | neutral→bear       | bear→neutral       | ✅ confirmed |
| 5 | bull→neutral       | neutral→bull       | ❌ not confirmed |
| 6 | bear→neutral       | neutral→bear       | ❌ not confirmed |

Pairs #5 and #6 (cycle repeat) do not occur in live data. After bull→neutral or bear→neutral the market always passes through at least one neutral→neutral before the next cycle opening. `MIN_NN_COUNT` reflects a structural property of the market, not just a safety parameter.

---

## 5. What Does NOT Change

- State machine (WAIT_PAIR → IN_NEUTRAL → READY → EXIT_WAIT)
- Transition names (neutral→bull, bear→neutral, etc.)
- MIN_NN_COUNT, ENGINE_RESET_AT
- P band constants (P_NEUTRAL_BULL=0.66, P_X_NEUTRAL=0.51, P_NEUTRAL_BEAR=0.14)
- ΔP_pair tracking (bull pair ΔP≈-0.15, bear pair ΔP≈+0.37)
- CSV output format

---

## 6. Market-Confirmed ΔP Events

Cycle repeat pairs (#5, #6) removed — not observed in live data.

| Previous transition | Transition detected | ΔP used |
|:--------------------|:--------------------|:-------:|
| neutral→neutral     | neutral→bull        | −0.34   |
| neutral→bull        | bull→neutral        | −0.15   |
| neutral→neutral     | neutral→bear        | −0.86   |
| neutral→bear        | bear→neutral        | +0.37   |

---

## 7. State Machine Events — ΔP and P per Bot Action

Every bot action in READY state is preceded by the neutral gap (neutral→neutral).
This means the "previous transition" at the moment of action is always neutral→neutral or one of the 4 confirmed pairs.
All bot events map to exactly the 4 confirmed ΔP values from table 6.

Note: CYCLE REPEAT was marked ❌ in table 4 as a direct pair (bull→neutral → neutral→bull).
In the state machine it always passes through the neutral gap first, making it neutral→neutral → neutral→bull — which IS confirmed (same ΔP as OPEN LONG/SHORT).

| Bot event              | Previous transition | Transition detected | P_prev | P_curr | ΔP    |
|:-----------------------|:--------------------|:--------------------|:------:|:------:|:-----:|
| NEUTRAL GAP            | neutral→neutral     | neutral→neutral     |  1.00  |  1.00  |  0.00 |
| OPEN LONG              | neutral→neutral     | neutral→bull        |  1.00  |  0.66  | −0.34 |
| PAIR CONFIRMED (LONG)  | neutral→bull        | bull→neutral        |  0.66  |  0.51  | −0.15 |
| NEUTRAL GAP n=1        | bull→neutral        | neutral→neutral     |  0.51  |  1.00  | +0.49 |
| NEUTRAL GAP n≥2        | neutral→neutral     | neutral→neutral     |  1.00  |  1.00  |  0.00 |
| NEUTRAL GAP n≥3        | neutral→neutral     | neutral→neutral     |  1.00  |  1.00  |  0.00 |
| CYCLE REPEAT (LONG)    | neutral→neutral     | neutral→bull        |  1.00  |  0.66  | −0.34 |
| OPPOSITE OPEN (LONG)   | neutral→neutral     | neutral→bear        |  1.00  |  0.14  | −0.86 |
| CLOSE LONG             | neutral→bear        | bear→neutral        |  0.14  |  0.51  | +0.37 |
| OPEN SHORT             | neutral→neutral     | neutral→bear        |  1.00  |  0.14  | −0.86 |
| PAIR CONFIRMED (SHORT) | neutral→bear        | bear→neutral        |  0.14  |  0.51  | +0.37 |
| NEUTRAL GAP n=1        | bear→neutral        | neutral→neutral     |  0.51  |  1.00  | +0.49 |
| NEUTRAL GAP n≥2        | neutral→neutral     | neutral→neutral     |  1.00  |  1.00  |  0.00 |
| NEUTRAL GAP n≥3        | neutral→neutral     | neutral→neutral     |  1.00  |  1.00  |  0.00 |
| CYCLE REPEAT (SHORT)   | neutral→neutral     | neutral→bear        |  1.00  |  0.14  | −0.86 |
| OPPOSITE OPEN (SHORT)  | neutral→neutral     | neutral→bull        |  1.00  |  0.66  | −0.34 |
| CLOSE SHORT            | neutral→bull        | bull→neutral        |  0.66  |  0.51  | −0.15 |

---

## 8. P Structural Constants — Tolerance Band

P_curr structural values at convergence, with tolerance band for reference.

| Transition      | P_curr | Tolerance band          |
|:----------------|:------:|:-----------------------:|
| neutral→bull    | 0.66   | [0.66 − tol, 0.66 + tol] |
| neutral→bear    | 0.14   | [0.14 − tol, 0.14 + tol] |
| bull→neutral    | 0.51   | [0.51 − tol, 0.51 + tol] |
| bear→neutral    | 0.51   | [0.51 − tol, 0.51 + tol] |
| neutral→neutral | 1.00   | [1.00 − tol, 1.00]        |

`tol` is a single tunable parameter. At full SKA convergence the bands are tight (live proof: ΔP_pair std ≈ ±0.004). Starting test value: tol = 0.025.
