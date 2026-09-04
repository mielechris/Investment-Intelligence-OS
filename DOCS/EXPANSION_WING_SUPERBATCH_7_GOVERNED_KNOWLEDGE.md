# Superbatch 7: Governed Investor Knowledge and Interview Pipeline

Status: fixture-first contracts only; providers, ingestion, transcription, archive persistence, and external requests are `NOT_ACTIVATED`.
Implementation batch cost: **$0**. Default daily and monthly provider ceilings are both **$0**.

## Source and rights boundary

Admissible records are attributable notes or short quotations linked to an official filing, shareholder letter,
lawfully obtained book note/excerpt, article, public interview, podcast, public video, or reviewed user interview.
Every record carries author, investor, publication/retrieval/point-in-time dates, type, HTTPS domain or explicit
synthetic-fixture locator, rights decisions, provenance, and SHA-256 content hash. Both permitted-use and rights
review must be `PERMITTED`; unknown rights fail closed. Paywall bypasses, confidential material, illegal copies,
complete copyrighted works, unattributed sources, and quotations over 280 characters are rejected.

The numeric quote ceiling is an internal conservative storage control, not a legal conclusion. The U.S. Copyright
Office says fair use is fact-specific and has no universal word-count rule. Rights review therefore remains human.

## Initial acquisition order

No acquisition occurs in this batch. Once rights, networking, and costs receive separate approval, the proposed
order is:

1. SEC EDGAR filings and issuer-hosted shareholder letters: public, first-party, point-in-time evidence.
2. Official investor/firm letters and university-hosted lectures: capture notes and limited quotations only.
3. Author/publisher-authorized books or lawfully owned copies: store governed notes, never complete text.
4. Official public interviews, podcasts, and videos with explicit terms: retain source pointers and short excerpts.
5. Licensed articles/research after license review; reject unclear reuse terms and paywall circumvention.
6. Jesse uploads only after consent, permitted-use, confidentiality exclusion, correction, speaker attribution,
   and Jesse approval are complete.

Professional coverage begins with Buffett, Munger, Lynch, Marks, Druckenmiller, Soros, Paul Tudor Jones, and
Greenblatt, followed by Gross (fixed income/Treasuries), Seykota (trend/futures), Asness (quantitative factors),
Rogers (commodities), and Ritter (IPOs). These are attributed hypothesis sources, never authorities or truth.

## Transcription provider decision (not selected)

| Option | Accuracy/diarization evidence to validate | Privacy/retention gate | Published cost signal (reviewed 2026-09-03) | Outage behavior | Decision |
|---|---|---|---|---|---|
| OpenAI Audio API | transcription endpoints exist; diarization and domain accuracy require fixture benchmark | eligible API controls exist, but account-specific retention must be approved | pricing must be rechecked at activation; unknown here | bounded timeout, two retries, then sanitized `UNAVAILABLE` | fail closed / not selected |
| Deepgram | Nova models and diarization require fixture benchmark | published compliance claims; exact retention/training terms require review | Nova-3 listed from $0.29/hour | bounded timeout, two retries, no provider fallback | candidate only |
| AssemblyAI | Universal models; speaker diarization listed as add-on | async audio deletion begins at 24 hours and may take up to 48; opt-out/metadata details require approval | Universal-2 $0.15/hour; diarization $0.02/hour | bounded timeout, two retries, no provider fallback | candidate only |
| Amazon Transcribe | batch/stream speaker diarization; finance vocabulary benchmark required | TLS/KMS/S3 controls; storage lifecycle and account region require approval | per-second pay-as-you-go; region price must be known before activation | bounded timeout, two retries, no provider fallback | candidate only |
| Local/offline model | must benchmark word and speaker error rates on consented fixtures | strongest content locality; model/license and hardware provenance still required | software/model/hardware cost currently unknown | local resource ceiling; fail closed on overload | candidate only |

Activation requires a fixed price sheet, diarization and accuracy fixture evaluation, deletion/retention terms,
training opt-out, region, encryption, outage contract, and legal/privacy review. Unknown price or rights is a hard
rejection. A future approved budget must replace the current $0 daily/monthly ceilings; no automatic overage or
cross-provider fallback is allowed.

Official references:

- OpenAI Audio API FAQ and platform data controls: https://help.openai.com/en/articles/7031512 and https://platform.openai.com/docs/models/default-usage-policies-by-endpoint
- Deepgram pricing: https://deepgram.com/pricing
- AssemblyAI pricing and retention: https://www.assemblyai.com/pricing/ and https://support.assemblyai.com/articles/2240096256-does-assemblyai-offer-zero-data-retention
- Amazon Transcribe feature, security, and encryption documentation: https://docs.aws.amazon.com/transcribe/latest/dg/feature-matrix.html and https://docs.aws.amazon.com/transcribe/latest/dg/data-encryption.html
- SEC EDGAR API boundary: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- U.S. Copyright Office fair-use guidance: https://www.copyright.gov/help/faq/faq-fairuse.html

## Activation gates

- human-approved source rights and interview consent;
- approved provider, exact current pricing, daily/monthly budgets, credentials plan, privacy/retention and license;
- isolated contract test plus accuracy/diarization acceptance on consented fixtures;
- durable encrypted storage design, deletion and audit policy;
- network egress allowlist, sanitized observability, queue/concurrency/retry/timeout controls;
- explicit operational change review and rollback;
- continued immutable false authority for broker, orders, paper-ledger writes, thresholds, credentials, and live execution.
