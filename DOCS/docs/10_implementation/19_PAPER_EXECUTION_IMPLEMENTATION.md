# Paper Execution Implementation

## Paper Adapter

Create interface:

```python
class ExecutionAdapter(Protocol):
    def submit(...): ...
    def cancel(...): ...
    def get_order(...): ...
    def get_fills(...): ...
    def get_positions(...): ...
    def get_account(...): ...
```

V0.1 implementation:

```text
InternalPaperExecutionAdapter
```

## Order Preconditions

Validate:

- PAPER environment;
- active thesis;
- active committee decision;
- active risk approval;
- fresh market data;
- supported instrument;
- kill switch inactive.

## Fill Model

V0.1 can use:

```text
market order:
  buy = ask or conservative bar proxy + slippage
  sell = bid or conservative bar proxy - slippage
```

Include:

- spread;
- slippage;
- fees;
- latency;
- partial fills where practical.

## Accounting Transaction

One fill transaction updates:

- fill;
- cash;
- lot;
- position;
- fees;
- portfolio state;
- audit;
- outbox.

If transaction fails, none commit.

## Reconciliation

Create scheduled reconciliation.

Any mismatch:

```text
critical alert
→ no new risk
→ incident if unresolved
```
