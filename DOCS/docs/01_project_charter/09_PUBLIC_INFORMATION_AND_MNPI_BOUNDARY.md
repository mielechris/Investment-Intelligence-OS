# Investment Intelligence OS
## Public Information and MNPI Boundary — v0.1

**Purpose:** Define the information boundary for all IIOS research, agents, datasets, tests, reports, and decisions.

**Operating rule:** Use lawful public or properly licensed information only.

This document is an internal engineering and governance boundary. It is not a substitute for professional legal or compliance advice before live or institutional deployment.

---

## 1. Allowed Information

IIOS may use information that is lawfully available and appropriately handled, including:

- official government websites and APIs;
- executive orders, presidential actions, memoranda, proclamations, and official remarks;
- congressional bills, actions, votes, hearings, and committee records;
- Federal Reserve releases, speeches, minutes, and testimony;
- public macroeconomic releases;
- public SEC filings;
- public CFTC reports;
- public USDA, NOAA, EIA, Treasury, OFAC, USTR, Commerce, and Federal Register data;
- public company filings, press releases, earnings calls, and investor presentations;
- licensed market data;
- reputable published news and research used within applicable rights;
- publicly disclosed fund letters and strategy descriptions;
- public ownership or transaction disclosures with their reporting lag preserved;
- academic research;
- public weather and geospatial data;
- public social-media posts when collected and used lawfully;
- user-created notes that contain no protected information;
- synthetic data and fictional test scenarios.

---

## 2. Prohibited Information

IIOS must not solicit, ingest, retain, process, or act on:

- material nonpublic information;
- confidential employer information;
- confidential client information;
- confidential supplier information;
- nonpublic transaction information;
- private tips from insiders;
- hacked or stolen data;
- leaked credentials;
- illegally intercepted communications;
- unauthorized private messages or emails;
- embargoed information obtained before lawful release;
- trade secrets;
- confidential contract terms;
- personal data collected without authority or need;
- data obtained in violation of license or terms;
- information whose provenance cannot be established after review.

---

## 3. Public Does Not Mean Real-Time

Public disclosures may contain significant delay.

Examples include:

- public fund holdings reported after the fact;
- insider transaction filings reported after execution;
- futures positioning reports reflecting an earlier measurement date;
- macroeconomic series later revised;
- meeting announcements published after the event;
- policy statements that precede formal implementation.

Every record must preserve:

- event date;
- publication date;
- retrieval date;
- market-available date;
- effective date where applicable;
- revision or reporting lag.

A delayed public record may be useful as context without being a current trading signal.

---

## 4. Information Intake Test

Before allowing a source into IIOS, answer:

1. Is the source lawfully accessible?
2. Is its publisher or provider identifiable?
3. Are usage rights or license conditions known?
4. Is the information public or properly licensed?
5. Is there any reason to believe it contains confidential, stolen, hacked, or embargoed material?
6. Can publication and market-availability time be established?
7. Can an immutable raw record be preserved?
8. Can the source be cited and audited?
9. Does the system need this information?
10. Is collection proportionate to the purpose?

If any answer creates doubt, quarantine the source.

---

## 5. Quarantine Process

When provenance, rights, or public status is uncertain:

1. Mark the record `QUARANTINED`.
2. Exclude it from retrieval, reasoning, training, testing, and decisions.
3. Preserve only the minimum metadata needed to review the issue.
4. Record why it was quarantined.
5. Assign a human reviewer.
6. Approve, restrict, or delete it.
7. Record the final disposition.

A model may not decide by itself that quarantined data is safe.

---

## 6. Accidental Receipt Procedure

If prohibited or potentially nonpublic information is received:

1. Stop analysis.
2. Do not copy it into project documents, prompts, tickets, or datasets.
3. Do not ask follow-up questions that expand the information.
4. Isolate or delete it according to applicable requirements.
5. Record the incident without reproducing the sensitive content.
6. Review whether any model, cache, log, or artifact retained it.
7. Obtain appropriate professional guidance if the incident is material.
8. Do not make or simulate a decision based on it.

---

## 7. Public Investor and Trading-Bot Research

IIOS may analyze public behavior, but must preserve limitations.

For any public holdings or trade analysis, record:

- disclosure type;
- reporting period;
- publication date;
- estimated execution window;
- known reporting lag;
- whether the disclosed position may be hedged;
- whether size, exit, derivatives, or related positions are unknown;
- whether the investor’s capital base and constraints differ from the user’s;
- alternative explanations.

A public trade is not automatically a recommendation.

---

## 8. Source Metadata Requirements

Every approved source must have:

- source ID;
- publisher;
- title or endpoint;
- URL or provider reference;
- source type;
- public or license classification;
- rights notes;
- retrieval method;
- retrieval timestamp;
- market-available timestamp logic;
- trust score;
- freshness expectation;
- revision behavior;
- retention rule;
- owner;
- review date.

---

## 9. Agent Requirements

Agents must:

- cite evidence IDs;
- avoid unsupported claims;
- distinguish public fact from inference;
- state disclosure lag;
- refuse quarantined data;
- flag uncertain provenance;
- abstain when source status is unclear.

Agents must not:

- ask for insider tips;
- infer that a private rumor is true because price moved;
- use unauthorized connectors;
- conceal source origin;
- treat leaked information as public merely because it appeared online.

---

## 10. Pre-Live Review

Before any live or institutional deployment, the information boundary must receive a separate review covering:

- securities-law considerations;
- investment-adviser or broker obligations where applicable;
- market-data licenses;
- alternative-data rights;
- privacy;
- retention;
- monitoring;
- incident response;
- user access;
- vendor contracts;
- jurisdiction.

V1 approval does not complete that future review.
