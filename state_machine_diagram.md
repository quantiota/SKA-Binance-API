## State Machine Diagram


### State Encoding

| State   | Code |
|---------|------|
| neutral | `00` |
| bull    | `01` |
| bear    | `10` |

Code `11` is undefined and never occurs.



### Transition Encoding

A transition A→B is a **4-bit word** `[a₁a₀b₁b₀]` (from-state | to-state):

The index is `prev_regime × 3 + regime` where `neutral=0, bull=1, bear=2`:

| Index | Transition       | 4-bit word |
|-------|-----------------|------------|
| 0     | neutral→neutral | `0000`     |
| 1     | neutral→bull    | `0001`     |
| 2     | neutral→bear    | `0010`     |
| 3     | bull→neutral    | `0100`     |
| 4     | bull→bull       | `0101`     | — never observed |
| 5     | bull→bear       | `0110`     |
| 6     | bear→neutral    | `1000`     |
| 7     | bear→bull       | `1001`     |
| 8     | bear→bear       | `1010`     | — never observed |


[Read More](https://github.com/quantiota/SKA-quantitative-finance/tree/main/ska_engine_c/binary_transition_space)

### Theoretical Foundation

The market operates as a question-answer structure encoded in 4-bit words. Every sequence is a grammatically complete sentence: a question asked, and an answer given.

The probe sequences (5760 and 10560) with Δp=0 are not anomalies. They are the market's way of saying: "I still need to complete the sentence." Even when there is no net price movement, the market refuses to leave the question unanswered. It goes through the full lawful loop just to give a grammatically correct "No" answer.

This is profound because of the chain rule: the question (neutral→bull or neutral→bear) has been asked. The market must give an answer that belongs to the question. It cannot stay silent or jump randomly. So it produces the probe — a zero-price-change sentence that still obeys the grammar perfectly.

The market needs this question-answer structure more than it needs price movement. Price is secondary. The sentence must be completed.

This is where the variational principle becomes visible: the market is not wandering through the 9 transitions — it follows paths that respect the grammar even when the zero-cost path in price space is available. The market cares more about answering the question correctly than about moving the price.

**Price is the registered answer. The question lives in the transition structure.**


### Version 1

From Wheeler's "It from Bit" — every sequence is a binary question with a binary answer, price is the registred answer.

**Sequences:**
- (39.1%) Question: "Is there buying demand?" `neutral-neutral → neutral-bull`  Answer: "Yes" `bull-neutral → neutral-neutral`  dp=+1  → LONG
- (38.6%) Question: "Is there selling pressure?" `neutral-neutral → neutral-bear`  Answer: "Yes" `bear-neutral → neutral-neutral`  dp=-1  → SHORT

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

---

### Version 2 — probe-aware, sequence-level decision

Direct jumps (bull-bear, bear-bull) are no longer ignored — they signal a probe sequence and trigger HOLD.

**Probe sequences:**
- (4.1%) Question: "Is there buying demand?" `neutral-neutral → neutral-bull`  Answer: "No" `bull-bear → bear-neutral → neutral-neutral`  dp=0  → HOLD LONG
- (4.4%) Question: "Is there selling pressure?" `neutral-neutral → neutral-bear`  Answer: "No" `bear-bull → bull-neutral → neutral-neutral`  dp=0  → HOLD SHORT

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
    B -->|"prev=2 curr=1"| DJ2["bear→bull\nMONITORED"]

    R -->|"prev=0 curr=2"| T5["neutral→bear\nP ≈ 0.14"]
    R -->|"prev=2 curr=2"| T6["bear→bear"]
    R -->|"prev=1 curr=2"| DJ1["bull→bear\nMONITORED"]

    T3 -->|"OPEN LONG"| WAIT_PAIR_L["WAIT_PAIR\nLONG"]
    T5 -->|"OPEN SHORT"| WAIT_PAIR_S["WAIT_PAIR\nSHORT"]

    %% --- LONG path ---
    WAIT_PAIR_L -->|"bull→neutral\npair confirmed"| IN_N_L["IN_NEUTRAL\ncounting neutral→neutral"]
    WAIT_PAIR_L -->|"bull→bear\nprobe detected"| PROBE_L["PROBE\nLONG held"]

    PROBE_L -->|"bear→neutral\nprobe complete"| READY_L["READY\nLONG"]

    IN_N_L -->|"n ≥ 10 then non-neutral"| READY_L

    READY_L -->|"neutral→bull\ncycle repeats"| WAIT_PAIR_L
    READY_L -->|"neutral→bear\nopposite opens"| EXIT_L["EXIT_WAIT\nLONG"]

    EXIT_L -->|"bear→neutral\n|P−0.51|≤0.0153"| CLOSE_L["CLOSE LONG"]
    EXIT_L -->|"bear→bull\nprobe detected"| PROBE_EXIT_L["PROBE_EXIT\nLONG held"]
    EXIT_L -->|"neutral→bull\ncycle repeats"| WAIT_PAIR_L

    PROBE_EXIT_L -->|"bull→neutral\nprobe complete → HOLD"| READY_L

    %% --- SHORT path ---
    WAIT_PAIR_S -->|"bear→neutral\npair confirmed"| IN_N_S["IN_NEUTRAL\ncounting neutral→neutral"]
    WAIT_PAIR_S -->|"bear→bull\nprobe detected"| PROBE_S["PROBE\nSHORT held"]

    PROBE_S -->|"bull→neutral\nprobe complete"| READY_S["READY\nSHORT"]

    IN_N_S -->|"n ≥ 10 then non-neutral"| READY_S

    READY_S -->|"neutral→bear\ncycle repeats"| WAIT_PAIR_S
    READY_S -->|"neutral→bull\nopposite opens"| EXIT_S["EXIT_WAIT\nSHORT"]

    EXIT_S -->|"bull→neutral\n|P−0.51|≤0.0153"| CLOSE_S["CLOSE SHORT"]
    EXIT_S -->|"bull→bear\nprobe detected"| PROBE_EXIT_S["PROBE_EXIT\nSHORT held"]
    EXIT_S -->|"neutral→bear\ncycle repeats"| WAIT_PAIR_S

    PROBE_EXIT_S -->|"bear→neutral\nprobe complete → HOLD"| READY_S
```
