# E10 — Research Backtesting and Learning

**Default priority:** P0/P1
**Tickets:** 12

| Ticket | Priority | Title | Dependencies |
|---|---|---|---|
| T101 | P0 | Implement dataset-manifest registry | T032,T027,T028 |
| T102 | P0 | Implement point-in-time dataset builder skeleton | T101,T055,T056 |
| T103 | P1 | Implement feature-definition registry | T032 |
| T104 | P1 | Implement label-definition registry | T032 |
| T105 | P0 | Implement baseline strategy library | T101 |
| T106 | P0 | Implement event-study engine V0.1 | T102,T105 |
| T107 | P0 | Implement backtest engine V0.1 | T102,T105,T055 |
| T108 | P1 | Implement walk-forward and holdout runner | T107 |
| T109 | P1 | Implement parameter sensitivity runner | T107 |
| T110 | P1 | Implement regime-segmented performance report | T107,T062 |
| T111 | P0 | Implement postmortem and outcome attribution service | T032,T098,T072 |
| T112 | P1 | Implement calibration and belief-update registry | T111,T030 |
