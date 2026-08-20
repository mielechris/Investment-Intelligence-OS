# Paper Execution Operations

## Preconditions

- PAPER environment;
- active thesis;
- valid committee decision;
- active risk approval;
- fresh market data;
- healthy paper adapter;
- no kill switch.

## Order Lifecycle Monitoring

Track:

- created;
- validated;
- risk authorized;
- submitted;
- accepted;
- partial fill;
- filled;
- cancelled;
- rejected;
- expired.

## Duplicate Protection

Every order intent uses an idempotency key.

Duplicate intent must not create a second order.

## Fill Review

Monitor:

- price;
- spread;
- slippage;
- fees;
- partial fills;
- timing.

## Reconciliation

At least daily:

- intents;
- orders;
- fills;
- positions;
- cash.

## Failure

A paper broker outage does not permit invented fills.
