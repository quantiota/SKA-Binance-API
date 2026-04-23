## State Machine Diagram

### Version 1

```mermaid
---
config:
  look: classic
  theme: base
  layout: elk
---
flowchart TD
    P["P(n) = exp(-|ΔH/H|)"]
    DP["ΔP(n) = P(n) - P(n-1)"]

    P --> DP

    DP -->|"|ΔP−(−0.34)|≤tol"| B["regime = 1\nbull"]
    DP -->|"|ΔP−(−0.86)|≤tol"| R["regime = 2\nbear"]
    DP -->|"else"| N["regime = 0\nneutral"]

    N -->|"prev=0 curr=0"| T0["neutral→neutral\nP ≈ 1.00"]
    N -->|"prev=1 curr=0"| T1["bull→neutral\nP ≈ 0.51"]
    N -->|"prev=2 curr=0"| T2["bear→neutral\nP ≈ 0.51"]

    B -->|"prev=0 curr=1"| T3["neutral→bull\nP ≈ 0.66"]
    B -->|"prev=1 curr=1"| T4["bull→bull"]
    B -->|"prev=2 curr=1"| DJ2["bear→bull\nIGNORED — direct jump"]

    R -->|"prev=0 curr=2"| T5["neutral→bear\nP ≈ 0.14"]
    R -->|"prev=2 curr=2"| T6["bear→bear"]
    R -->|"prev=1 curr=2"| DJ1["bull→bear\nIGNORED — direct jump"]

    T3 -->|"OPEN LONG"| WAIT_PAIR_L["WAIT_PAIR\nLONG"]
    T5 -->|"OPEN SHORT"| WAIT_PAIR_S["WAIT_PAIR\nSHORT"]

    WAIT_PAIR_L -->|"bull→neutral\npair confirmed"| IN_N_L["IN_NEUTRAL\ncounting neutral→neutral"]
    WAIT_PAIR_S -->|"bear→neutral\npair confirmed"| IN_N_S["IN_NEUTRAL\ncounting neutral→neutral"]

    IN_N_L -->|"n ≥ 10 then non-neutral"| READY_L["READY\nLONG"]
    IN_N_S -->|"n ≥ 10 then non-neutral"| READY_S["READY\nSHORT"]

    READY_L -->|"neutral→bull\ncycle repeats"| WAIT_PAIR_L
    READY_L -->|"neutral→bear\nopposite opens"| EXIT_L["EXIT_WAIT\nLONG"]
    EXIT_L -->|"bear→neutral\n|P−0.51|≤0.0153"| CLOSE_L["CLOSE LONG"]
    EXIT_L -->|"neutral→bull\ncycle repeats"| WAIT_PAIR_L

    READY_S -->|"neutral→bear\ncycle repeats"| WAIT_PAIR_S
    READY_S -->|"neutral→bull\nopposite opens"| EXIT_S["EXIT_WAIT\nSHORT"]
    EXIT_S -->|"bull→neutral\n|P−0.51|≤0.0153"| CLOSE_S["CLOSE SHORT"]
    EXIT_S -->|"neutral→bear\ncycle repeats"| WAIT_PAIR_S
```


### Version 2 — probe-aware, sequence-level decision

Direct jumps (bull-bear, bear-bull) are no longer ignored — they signal a probe sequence and trigger HOLD.

**Probe sequences:**
- `5760`  : `0000 → neutral-bull → bull-bear → bear-neutral → 0000`  dp=0  → HOLD LONG
- `10560` : `0000 → neutral-bear → bear-bull → bull-neutral → 0000`  dp=0  → HOLD SHORT

```mermaid
---
config:
  look: classic
  theme: base
  layout: elk
---
flowchart TD
    P["P(n) = exp(-|ΔH/H|)"]
    DP["ΔP(n) = P(n) - P(n-1)"]

    P --> DP

    DP -->|"|ΔP−(−0.34)|≤tol"| B["regime = 1\nbull"]
    DP -->|"|ΔP−(−0.86)|≤tol"| R["regime = 2\nbear"]
    DP -->|"else"| N["regime = 0\nneutral"]

    N -->|"prev=0 curr=0"| T0["neutral-neutral\nP ≈ 1.00"]
    N -->|"prev=1 curr=0"| T1["bull-neutral\nP ≈ 0.51"]
    N -->|"prev=2 curr=0"| T2["bear-neutral\nP ≈ 0.51"]

    B -->|"prev=0 curr=1"| T3["neutral-bull\nP ≈ 0.66"]
    B -->|"prev=1 curr=1"| T4["bull-bull\nMONITORED"]
    B -->|"prev=2 curr=1"| DJ2["bear-bull\nMONITORED"]

    R -->|"prev=0 curr=2"| T5["neutral-bear\nP ≈ 0.14"]
    R -->|"prev=2 curr=2"| T6["bear-bear\nMONITORED"]
    R -->|"prev=1 curr=2"| DJ1["bull-bear\nMONITORED"]

    T3 -->|"OPEN LONG"| WAIT_PAIR_L["WAIT_PAIR\nLONG"]
    T5 -->|"OPEN SHORT"| WAIT_PAIR_S["WAIT_PAIR\nSHORT"]

    %% --- LONG path ---
    WAIT_PAIR_L -->|"bull-neutral\npair confirmed"| IN_N_L["IN_NEUTRAL\ncounting neutral-neutral"]
    WAIT_PAIR_L -->|"bull-bear\nprobe detected"| PROBE_L["PROBE\nLONG held"]

    PROBE_L -->|"bear-neutral\nprobe complete"| READY_L["READY\nLONG"]

    IN_N_L -->|"n ≥ 10 then non-neutral"| READY_L

    READY_L -->|"neutral-bull\ncycle repeats"| WAIT_PAIR_L
    READY_L -->|"neutral-bear\nopposite opens"| EXIT_WAIT_L["EXIT_WAIT\nLONG"]

    EXIT_WAIT_L -->|"bear-neutral\n|P−0.51|≤0.0153"| CLOSE_L["CLOSE LONG"]
    EXIT_WAIT_L -->|"bear-bull\nprobe detected"| PROBE_EXIT_L["PROBE_EXIT\nLONG held"]
    EXIT_WAIT_L -->|"neutral-bull\ncycle repeats"| WAIT_PAIR_L

    PROBE_EXIT_L -->|"bull-neutral\nprobe complete → HOLD"| READY_L

    %% --- SHORT path ---
    WAIT_PAIR_S -->|"bear-neutral\npair confirmed"| IN_N_S["IN_NEUTRAL\ncounting neutral-neutral"]
    WAIT_PAIR_S -->|"bear-bull\nprobe detected"| PROBE_S["PROBE\nSHORT held"]

    PROBE_S -->|"bull-neutral\nprobe complete"| READY_S["READY\nSHORT"]

    IN_N_S -->|"n ≥ 10 then non-neutral"| READY_S

    READY_S -->|"neutral-bear\ncycle repeats"| WAIT_PAIR_S
    READY_S -->|"neutral-bull\nopposite opens"| EXIT_WAIT_S["EXIT_WAIT\nSHORT"]

    EXIT_WAIT_S -->|"bull-neutral\n|P−0.51|≤0.0153"| CLOSE_S["CLOSE SHORT"]
    EXIT_WAIT_S -->|"bull-bear\nprobe detected"| PROBE_EXIT_S["PROBE_EXIT\nSHORT held"]
    EXIT_WAIT_S -->|"neutral-bear\ncycle repeats"| WAIT_PAIR_S

    PROBE_EXIT_S -->|"bear-neutral\nprobe complete → HOLD"| READY_S
```