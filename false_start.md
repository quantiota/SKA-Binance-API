

# False Start 

## False Start — Direct bull→bear Transition

  The market confirms two bull pairs correctly (neutral→bull→neutral), then opens a third LONG at     
  neutral→bull. Instead of confirming with bull→neutral (P ≈ 0.51), the transition fires directly
  bull→bear (P ≈ 0.018) — a structurally rare event that signals the expected confirmation will never 
  arrive. The position closes at a loss on bear→neutral. The low probability of bull→bear is the structural fingerprint of a false start, detectable from the entropy dynamics before
  the loss is realized.


```mermaid
---
config:
  look: classic
  theme: base
  layout: elk
---

block-beta
  columns 24
  B4["neutral→neutral\nP ≈ 1.00"] B5["neutral→neutral\nP ≈ 1.00"] B6["neutral→neutral\nP ≈ 1.00"] B1["neutral→neutral\nP ≈ 1.00"] space space
  B10["neutral→neutral\nP ≈ 1.00"] B11["neutral→neutral\nP ≈ 1.00"] B12["neutral→neutral\nP ≈ 1.00"] B7["neutral→neutral\nP ≈ 1.00"] space space
  B19["neutral→neutral\nP ≈ 1.00"] B20["neutral→neutral\nP ≈ 1.00"] B21["neutral→neutral\nP ≈ 1.00"] B22["neutral→neutral\nP ≈ 1.00"] space space space
  B24["neutral→neutral\nP ≈ 1.00"] B25["neutral→neutral\nP ≈ 1.00"] 
  space:21
  space space space space space space space   space  space  space B2["neutral→bull\nP ≈ 0.66"] space    space  space  space space B8["neutral→bull\nP ≈ 0.66"] space space space  space  space B18["neutral→bull\nP ≈ 0.66"] 
  space:24
  space space space space space space space space space space  space  space      B3["bull→neutral\nP ≈ 0.51"]  space  space space space space  B9["bull→neutral\nP ≈ 0.51"] space space
  space:1
  space space space  B23["bear→neutral\nP ≈ 0.51"]
  
  space:90
  space space space space   B13["bull→bear\nP ≈ 0.018"]


  classDef nn fill:#c0d8ff,stroke:#999,color:#333
  classDef neutralbull fill:#39cccc,stroke:#007c9e,color:#fff
  classDef bullneutral fill:#ffdc00,stroke:#e6a800,color:#333
  classDef bullbear fill:#ff3333,stroke:#ff333,color:#333
  classDef bearneutral fill:#ff851b,stroke:#ff333,color:#333


  class B1,B4,B5,B6,B7,B10,B11,B12,B14,B15,B16,B17,B19,B20,B21,B22,B24,B25 nn
  class B2,B8,B18 neutralbull
  class B3,B9 bullneutral
  class B13 bullbear
  class B23 bearneutral
  ```


## False Start — Direct bear→bull Transition

 The market confirms two bear pairs correctly (neutral→bear→neutral), then opens a third SHORT at    
  neutral→bear. Instead of confirming with bear→neutral (P ≈ 0.51), the transition fires directly     
  bear→bull (P ≈ 0.45) — a structurally rare path through the grammar that signals the expected       
  confirmation will never arrive. The position closes at a loss on bull→neutral. The low frequency of
  bear→bull is the structural fingerprint of a false start, detectable from the entropy dynamics
  before the loss is realized.


```mermaid
---
config:
  look: classic
  theme: base
  layout: elk
---

 block-beta                                                                                                                                                 
    columns 24                                                                                                                                               
    C4["neutral→neutral\nP ≈ 1.00"] C5["neutral→neutral\nP ≈ 1.00"] C6["neutral→neutral\nP ≈ 1.00"] C1["neutral→neutral\nP ≈ 1.00"] space space              
    C10["neutral→neutral\nP ≈ 1.00"] C11["neutral→neutral\nP ≈ 1.00"] C12["neutral→neutral\nP ≈ 1.00"] C7["neutral→neutral\nP ≈ 1.00"] space space       
    C13["neutral→neutral\nP ≈ 1.00"] C14["neutral→neutral\nP ≈ 1.00"] C15["neutral→neutral\nP ≈ 1.00"] C16["neutral→neutral\nP ≈ 1.00"] space space  space
    C19["neutral→neutral\nP ≈ 1.00"] C20["neutral→neutral\nP ≈ 1.00"]
    space:50                                                                                                                                               
    space space space space space space C3["bear→neutral\nP ≈ 0.51"] space space space space space C9["bear→neutral\nP ≈ 0.51"]  space  space space  space  space   space  C22["bull→neutral\nP ≈ 0.51"]
    space:46  
    C17["bear→bull\nP ≈ 0.45"]                          
    space:102                                                                                                                                               
    space space space space C2["neutral→bear\nP ≈ 0.14"] space space space space space C8["neutral→bear\nP ≈ 0.14"] space space  space space space   C21["neutral→bear\nP ≈ 0.14"]
                                                                                                                                                             
    classDef nn fill:#c0d8ff,stroke:#999,color:#333                                                                                                          
    classDef nb2 fill:#f012be,stroke:#c00090,color:#fff                                                                                                      
    classDef bn2 fill:#ff851b,stroke:#cc5500,color:#333 
    classDef bb fill:#0074d9,stroke:#cc5500,color:#333     
    classDef bn fill:#ffdc00,stroke:#cc5500,color:#333                                                                                                   
                                                                                                                                                           
    class C1,C4,C5,C6,C7,C10,C11,C12,C13,C14,C15,C16,C17,C19,C20 nn                                                                                                                      
    class C2,C8,C21 nb2
    class C3,C9 bn2 
    class C17  bb
    class C22  bn
    ```
