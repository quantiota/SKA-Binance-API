# False Start Panel — Observed Cases

Forensic archive of false starts captured on the live Grafana panel.
Each entry records the transition sequence, P values, and PnL observed in real time.

---

## Format

```
Date       : UTC timestamp of the loop
Trade ID   : Binance trade_id at the false start transition
Sequence   : transition path observed
P values   : P at each transition
```

---

## Cases

<!-- Add new entries below as observed -->

---

### Case 1 — Bull False Start 

**Observed sequence** (trade_id window 1607297434–1607297456):

- `neutral→neutral` P = 1.00 — extended neutral gap
- `neutral→bull`    P ≈ 0.66 — at ~1607297440
- `bull→neutral`    P ≈ 0.54 — bull pair 1 complete ✓
- `neutral→bear`    P ≈ 0.15 — at ~1607297442
- `bear→bull`       P ≈ 0.45 — at ~1607297443
- `bull→bear`       P ≈ 0.02 — at ~1607297444
- `bear→neutral`    P ≈ 0.51 — at ~1607297445
- `neutral→bull`    P ≈ 0.66 — at ~1607297446
- `bull→neutral`    P ≈ 0.54 — bull pair 2 complete ✓
- `neutral→neutral` P = 1.00 — neutral gap resumes

All 7 transition types observed within ~22 trade IDs.

![False Start Case 1](screenshot_case1.png)

**Inner sequence** (between bull pair 1 and bull pair 2):

```python
{
    "date": "2026-04-14T11:37:30.746Z",
    "trade_id_window": [1607297442, 1607297445],
    "sequence": [
        {"transition": "neutral→bear", "P": 0.15},
        {"transition": "bear→bull",    "P": 0.45},
        {"transition": "bull→bear",    "P": 0.02},
        {"transition": "bear→neutral", "P": 0.51}
    ]
}
```

### Case 2 — 2026-04-14T12:21:45.115Z

**Observed sequence** (trade_id window 1607313366–1607313382):

- `neutral→neutral` P = 1.00 — extended neutral gap
- `neutral→bear`    P ≈ 0.15 — at ~1607313371
- `bear→neutral`    P ≈ 0.51 — bear pair complete ✓
- `neutral→bull`    P ≈ 0.66 — at ~1607313373
- `bull→bear`       P ≈ 0.02 — at ~1607313374
- `bear→bull`       P ≈ 0.45 — at ~1607313375
- `bull→neutral`    P ≈ 0.52 — at ~1607313376
- `neutral→neutral` P = 1.00 — neutral gap resumes

![False Start Case 1](screenshot_case2.png)

**Inner sequence** (between bear pair and bull→neutral close):

```python
{
    "date": "2026-04-14T12:21:45.115Z",
    "trade_id_window": [1607313373, 1607313376],
    "sequence": [
        {"transition": "neutral→bull", "P": 0.66},
        {"transition": "bull→bear",    "P": 0.02},
        {"transition": "bear→bull",    "P": 0.45},
        {"transition": "bull→neutral", "P": 0.52}
    ]
}
```
---


### Case 3 — 2026-04-14T12:44:51.600Z

**Observed sequence** (trade_id window 1607321228–1607321268):

- `neutral→neutral` P = 1.00 — extended neutral gap
- `neutral→bear`    P ≈ 0.15 — at ~1607321235
- `bear→neutral`    P ≈ 0.51 — bear pair complete ✓
- `neutral→bull`    P ≈ 0.66 — at ~1607321242
- `neutral→bear`    P ≈ 0.15 — at ~1607321244
- `bear→bull`       P ≈ 0.45 — at ~1607321246
- `bull→bear`       P ≈ 0.02 — at ~1607321247
- `bear→neutral`    P ≈ 0.51 — at ~1607321250
- `neutral→bear`    P ≈ 0.15 — at ~1607321266
- `bear→neutral`    P ≈ 0.51 — bear pair 2 complete ✓
- `bull→neutral`    P ≈ 0.51 — at ~1607321268 — **different close** (no preceding neutral→bull)

![Case 3](screenshots_case3.png)

**Difference from Case 1**: Case 1 closes with a confirmed `neutral→bull` → `bull→neutral` pair. Here the close is `bull→neutral` appearing without a preceding `neutral→bull` — the open of the bull leg is absent, only the close arrives.

**Inner sequence** (between bear pair 1 and close):

```python
{
    "date": "2026-04-14T12:44:51.600Z",
    "trade_id_window": [1607321242, 1607321268],
    "sequence": [
        {"transition": "neutral→bull", "P": 0.66},
        {"transition": "neutral→bear", "P": 0.15},
        {"transition": "bear→bull",    "P": 0.45},
        {"transition": "bull→bear",    "P": 0.02},
        {"transition": "bear→neutral", "P": 0.51},
        {"transition": "neutral→bear", "P": 0.15},
        {"transition": "bear→neutral", "P": 0.51},
        {"transition": "bull→neutral", "P": 0.51}
    ]
}
```