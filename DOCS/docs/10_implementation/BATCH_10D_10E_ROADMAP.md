# Batch 10D / 10E Roadmap

## Batch 10D — Closed-Loop Paper Portfolio

Goal: prove IIOS can operate the governed $10,000 paper fund as one closed loop without adding live-capital authority.

### 10D scope

1. **Paper Fund → Portfolio Context Bridge**
   - Current governed paper NAV, cash, positions, exact-ticker overlap and known sector overlap become first-party Portfolio Context.
   - Cash-only is a valid governed portfolio state.
   - The bridge may inform Portfolio/Risk/Deep Watch but cannot create an order.

2. **Closed-loop case lineage**
   - Discovery → nine desks → Historical Pattern → Committee → Risk → qualification → capital → paper authorization/execution → monitoring → Deep Watch → outcome/learning.
   - Rejections and WATCH states remain first-class outcomes.

3. **Command visibility**
   - Surface portfolio context, Deep Watch obligations, historical rechecks, rejection reasons, paper NAV/positions and learning outcomes.

4. **Operational resilience**
   - Provider/quota/circuit status is explicit and fail-closed.

5. **Acceptance**
   - A fully valid result may remain $10,000 cash / 0 positions.

## Options during 10D — Shadow Observation Only

Options are added as an observed market-expression layer, not an executable strategy.

Existing governed OCC open-interest positioning remains context only. During 10D, IIOS may collect/retain options observations and compare them with equity outcomes, but:

- no option contract selection authority;
- no strike/expiration recommendation authority;
- no option paper orders;
- no naked short options;
- no 0DTE execution;
- no options override of Committee, Risk, Capital or equity paper execution.

## Batch 10E — Governed Options Intelligence + Paper Execution

Only after 10D acceptance and sufficient shadow observations.

Initial permitted paper strategies:

- long calls;
- long puts;
- defined-risk bull call spreads;
- defined-risk bear put spreads;
- covered calls only when the governed paper portfolio owns the underlying.

Initial prohibited strategies:

- naked short calls or puts;
- undefined-risk structures;
- 0DTE;
- live options execution.

10E must add governed contract/chain data, bid/ask and liquidity checks, expiration/strike selection, Greeks, implied-volatility regime, event-window analysis, realistic fill/slippage modeling, max-loss sizing and options-specific outcome attribution before any option paper order is permitted.

## Authority boundary

Options observation is research context. Equities remain the only paper-capital expression during 10D. Live execution remains false.