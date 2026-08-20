# E06 — World Model and Evidence

**Default priority:** P0
**Tickets:** 10

| Ticket | Priority | Title | Dependencies |
|---|---|---|---|
| T057 | P0 | Implement entity registry repository and service | T028 |
| T058 | P0 | Implement entity resolution pipeline | T057 |
| T059 | P1 | Implement entity merge/split audit operations | T057 |
| T060 | P0 | Implement entity relationship service | T057,T058 |
| T061 | P0 | Implement policy lifecycle state projector | T028,T056,T060 |
| T062 | P0 | Implement world-state snapshot builder | T057,T060,T050 |
| T063 | P0 | Implement evidence object creation service | T029,T028 |
| T064 | P0 | Implement claim and evidence-link service | T063 |
| T065 | P1 | Implement evidence deduplication and independence clustering | T063,T050 |
| T066 | P0 | Implement evidence retraction propagation | T064 |
