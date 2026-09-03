# Investor Intelligence acquisition and interview contracts

Status: contract implementation with deterministic local processing; external acquisition is `NOT_ACTIVATED`.

## Pipeline

The source registry and professional profiles require identity, attribution, dates, source type, public/user-provided status, permitted use, rights review, representation class, SHA-256 content identity, provenance, applicable assets/regimes, freshness, and human-review state. The queue deduplicates by source identity and has a zero-dollar default ceiling. It never performs network work.

Normalization permits only reviewed content, collapses text deterministically, limits quotations to 280 characters, and rejects complete copyrighted works, paywalled material, unknown rights, and oversized inputs. Claims are explicitly `DIRECT`, `PARAPHRASED`, or `INFERRED`. Contradictions are review tasks, not automatically resolved facts. Philosophy classification produces hypotheses only. Failure cases preserve evidence known at decision time, invalidation, outcome, and skill-versus-luck review.

Judgment Foundry and Pattern Lab handoffs are blocked without human approval. Pattern handoff additionally requires point-in-time locking and always prohibits future information. Neither handoff auto-writes or auto-runs.

## Jesse/professional portal

Recording or processing requires consent, a permitted-use selection, and confidential employer/client exclusion. Audio, video, and text are allowed only after those gates. Approval additionally requires corrected transcript text, speaker attribution, and professional approval. MAX owns orchestration; specialist follow-up routing covers wins/losses, evidence known at decision time, sizing, holding period, invalidation, exit, regime, and skill versus luck.

The repository contains the listed Jesse themes as requested design leads, but the audit found no attributable source-controlled transcript establishing them as Jesse statements. They therefore remain `SOURCE_REVIEW_REQUIRED`, are not placed in the Judgment Bank, and are not treated as verified evidence.

## Curated acquisition plans

| Profile | Contrasting hypothesis to test | Initial lawful sources | Status |
|---|---|---|---|
| Buffett / Munger | durable quality, intrinsic value, capital allocation | shareholder letters, filings, attributable talks | NOT_ACTIVATED |
| Peter Lynch | understandable businesses and growth relative to price | public lectures/interviews, attributable writing notes | NOT_ACTIVATED |
| Howard Marks | cycles, credit and risk premiums | public memos and interviews | NOT_ACTIVATED |
| Druckenmiller | macro concentration and liquidity | public interviews/conferences | NOT_ACTIVATED |
| Soros | reflexivity and falsifiable positioning | public lectures/interviews and lawful notes | NOT_ACTIVATED |
| Paul Tudor Jones | macro risk control and trend | public interviews/conferences | NOT_ACTIVATED |
| Greenblatt | systematic value/quality hypotheses | public lectures, papers, lawful notes | NOT_ACTIVATED |
| Trend followers | time-series momentum and crisis behavior | manager papers and academic research | NOT_ACTIVATED |
| Academic factors | factor definitions, publication and implementation decay | original papers and replication studies | NOT_ACTIVATED |
| Fixed-income specialists | duration, credit, curve and liquidity | public letters, research, lectures | NOT_ACTIVATED |
| IPO specialists | issuance, lockups and seasoning | filings, prospectuses, academic research | NOT_ACTIVATED |
| Failure cases | survivorship, leverage, liquidity and thesis invalidation | attributable postmortems and primary records | NOT_ACTIVATED |

Fame never confers validation. Every profile claim remains a hypothesis until source, point-in-time, contradiction, and human-review gates pass.
