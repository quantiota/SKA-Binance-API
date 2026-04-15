
## Binary Transition Space

We believe—like John Archibald Wheeler—that the ultimate foundation of reality is information:

> "It from bit symbolizes the idea that every item of the physical world has at bottom—a very deep bottom, in most instances—an immaterial source and explanation; that what we call reality arises, in the last analysis, from the posing of yes-no questions and the registering of equipment-evoked responses; in short, that all things physical are information-theoretic in origin and that this is a participatory universe."

*John Archibald Wheeler, "Information, Physics, Quantum: The Search for Links" (1989/1990).*

---

## State Encoding

| State   | Code |
|---------|------|
| neutral | `00` |
| bull    | `01` |
| bear    | `10` |

Code `11` is undefined and never occurs.

---

## Transition Encoding

A transition A→B is a **4-bit word** `[a₁a₀b₁b₀]` (from-state | to-state):

| Index | Transition       | 4-bit word |
|-------|-----------------|------------|
| 0     | neutral→neutral | `0000`     |
| 1     | neutral→bull    | `0001`     |
| 2     | neutral→bear    | `0010`     |
| 3     | bull→neutral    | `0100`     |
| 4     | bear→neutral    | `1000`     |
| 5     | bull→bear       | `0110`     |
| 6     | bear→bull       | `1001`     |
| 7     | bull→bull       | `0101`     | — never observed |
| 8     | bear→bear       | `1010`     | — never observed |

---

## Composition ∘

`t₁ ∘ t₂` is valid when the to-state of `t₁` equals the from-state of `t₂`. The result:

```
t₁ ∘ t₂ = (t₁ AND 1100) OR (t₂ AND 0011)
```

Example: `neutral→neutral ∘ neutral→bull`

```
(0000 AND 1100) OR (0001 AND 0011) = 0000 OR 0001 = 0001  (neutral→bull)
```

A sequence is grammatically valid if and only if every consecutive pair composes.

---

## Binary Vector

The binary vector of a sequence maps it to a point in `{0,1}⁹` — one bit per transition type:

```
bv(S) = OR of all 4-bit word indices present in S
```

**Matching:** sequence `S` contains pattern `P` if and only if:

```
bv(S) AND bv(P) == bv(P)
```
