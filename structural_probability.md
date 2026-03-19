# Structural Probability

## Definition

At each tick n, the SKA engine computes an entropy value H.
The probability P is derived from the relative entropy change between two consecutive ticks:

```
P(n) = exp(−|ΔH/H|)   where   ΔH/H = (H(n) − H(n−1)) / H(n)

P(n) ∈ (0, 1]
```

- `|ΔH/H|` large  →  P close to 0  →  strong structural change
- `|ΔH/H|` small  →  P close to 1  →  entropy barely moving

---

## Regime Classification

At each tick, the regime is determined by the drop in P relative to the previous tick:

```
P(n) < P(n−1) − 0.221                →  bear    (large drop)
P(n−1) − 0.221  ≤  P(n)  <  P(n−1) − 0.148  →  bull    (moderate drop)
P(n)  ≥  P(n−1) − 0.148              →  neutral
```

Both bull and bear open on a drop in P. The magnitude of the drop distinguishes them.

---

## ΔP for a Paired Regime Transition

A trade is a **pair of two transitions**: an opening and a closing.
ΔP is defined specifically within this pair:

```
ΔP = P(n) − P(n−1)

  where  n−1 = opening transition tick  (neutral→bull  or  neutral→bear)
         n   = closing transition tick  (bull→neutral  or  bear→neutral)
```

ΔP is not a tick-by-tick quantity. It is the change in P between the
**two regime ticks of the same pair**.

---

## ΔP in Each Paired Regime

### Bull pair

```
n−1  :  neutral → bull   (LONG entry)    P(n−1) ≈ 0.82
n    :  bull → neutral   (LONG exit)     P(n)   ≈ 0.80

ΔP_bull = P(n) − P(n−1) = 0.80 − 0.82 = −0.02   →   negative
```

P continued to fall between the opening and closing transitions.
The closing is not a recovery — it is where the drift slowed below the threshold.

---

### Bear pair

```
n−1  :  neutral → bear   (SHORT entry)   P(n−1) ≈ 0.56
n    :  bear → neutral   (SHORT exit)    P(n)   ≈ 0.75

ΔP_bear = P(n) − P(n−1) = 0.75 − 0.56 = +0.19   →   positive
```

P rebounded between the opening and closing transitions.
The closing is an active recovery — the entropy shock has resolved.

---

## The Opposite Sign

| Pair  | P at opening | P at closing | ΔP        | Nature               |
|-------|-------------|--------------|-----------|----------------------|
| Bull  | ≈ 0.82      | ≈ 0.80       | **< 0**   | drift — P falls through |
| Bear  | ≈ 0.56      | ≈ 0.75       | **> 0**   | shock — P snaps back |

Both pairs open with a drop in P.
The sign of ΔP across the pair is what separates them:
- Bull: P **drifts lower** — the entropy change is sustained
- Bear: P **recovers** — the entropy shock was brief and violent

---

## Trading Logic

| Code | Transition     | Action       |
|------|----------------|--------------|
| 1    | neutral → bull | LONG entry   |
| 3    | bull → neutral | LONG exit    |
| 2    | neutral → bear | SHORT entry  |
| 6    | bear → neutral | SHORT exit   |

Constants:

| Constant       | Value  |
|----------------|--------|
| BULL_THRESHOLD | 0.148  |
| BEAR_THRESHOLD | 0.221  |
