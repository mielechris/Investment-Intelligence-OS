# Investment Intelligence OS
## Security, Privacy, and Secrets Architecture — v0.1

---

## 1. Security Objective

Protect:

- credentials;
- source rights;
- system integrity;
- decision lineage;
- portfolio state;
- model tools;
- audit history;
- future broker authority.

The most important V1 control is preventing a research or paper system from accidentally becoming a live execution system.

---

## 2. Threat Model

Primary threats include:

- committed credentials;
- malicious or compromised source content;
- prompt injection;
- unauthorized tool use;
- model data exfiltration;
- forged webhooks;
- dependency compromise;
- database modification;
- duplicate or unauthorized orders;
- environment confusion;
- stale or corrupted data;
- unauthorized public or nonpublic information;
- lost or stolen device;
- weak backup protection.

---

## 3. Identity

Every human and service action has an identity.

Initial identities:

- owner user;
- API service;
- worker service;
- scheduler service;
- migration process;
- backup process;
- agent identity;
- external provider identity.

Shared anonymous write access is prohibited.

---

## 4. Least Privilege

Examples:

- frontend cannot access database;
- API cannot read raw secret values after startup unless required;
- connectors access only assigned source credentials;
- agent tools are allow-listed;
- model gateway cannot change risk policy;
- risk engine cannot rewrite evidence;
- paper adapter has no live credentials;
- backup process receives read and write permissions appropriate to backup only.

---

## 5. Secret Management

Secrets include:

- API keys;
- database passwords;
- object-storage keys;
- model-provider keys;
- broker tokens;
- session-signing keys;
- encryption keys.

Rules:

- never commit secrets;
- never place secrets in screenshots or docs;
- never log secrets;
- use environment injection or secret manager;
- provide `.env.example` with placeholders only;
- rotate compromised secrets;
- separate environment credentials;
- future live credentials are isolated from paper.

---

## 6. Encryption

Use:

- encrypted transport for external and future remote communication;
- encryption at rest from storage provider where available;
- encrypted backups;
- secure local-device posture;
- protected secret storage.

The architecture records where encryption terminates.

---

## 7. Prompt Injection and Untrusted Content

External content may contain instructions intended to manipulate an agent.

Controls:

- treat source text as quoted data;
- isolate system instructions;
- allow-list tools;
- prohibit source text from changing authority;
- strip active content;
- do not execute code from documents;
- validate structured output;
- verify cited evidence;
- limit model context;
- redact secrets;
- monitor suspicious tool requests.

---

## 8. Model Data Boundary

Before sending data to a model provider:

- verify provider is approved;
- verify source rights permit the use;
- remove secrets;
- remove quarantined or prohibited data;
- minimize payload;
- record provider and model;
- follow retention settings;
- record request purpose.

A model provider is an external processor, not an internal trusted component.

---

## 9. Dependency and Supply-Chain Security

Controls:

- locked dependencies;
- dependency review;
- vulnerability scanning;
- license review;
- minimal packages;
- verified container images;
- secret scanning;
- static analysis;
- protected main branch;
- reproducible builds where practical.

Do not add a package merely to avoid writing a small, clear function.

---

## 10. Database Security

- separate roles by process;
- no public exposure by default;
- least-privilege grants;
- migration role separated where practical;
- audit privileged actions;
- encrypted connection when remote;
- backup access restricted;
- direct manual writes discouraged and audited.

---

## 11. API Security

- authenticated owner;
- secure session or token handling;
- CORS allow-list;
- CSRF control where applicable;
- request validation;
- rate limits;
- body-size limits;
- no secrets in URLs;
- stable errors without stack traces;
- authorization on every command.

---

## 12. Object-Storage Security

- private bucket or local private storage;
- no public object listing;
- controlled access;
- immutable or versioned raw objects;
- encryption;
- retention policy;
- content-type handling;
- malware or active-content caution for downloaded files.

---

## 13. Audit Security

Audit events should be append-only from normal application roles.

Record:

- actor;
- action;
- resource;
- time;
- environment;
- correlation ID;
- before and after references;
- reason;
- code and model version.

Audit logs must not become a secret leak.

---

## 14. Environment Safety

The environment is enforced in:

- configuration;
- database;
- execution adapter;
- API authorization;
- UI display;
- audit event;
- order record.

One mislabeled UI banner cannot convert paper into live.

---

## 15. Incident Handling

Security incident sequence:

1. activate stand-down if integrity may be affected;
2. preserve evidence;
3. revoke or rotate credentials;
4. isolate affected process;
5. inspect audit and logs;
6. assess affected decisions and data;
7. repair and validate;
8. document incident;
9. test prevention;
10. explicitly resume.

---

## 16. Privacy and Data Minimization

IIOS should avoid unnecessary personal data.

Store only what supports:

- public entity identity;
- source provenance;
- authentication;
- audit;
- project operation.

Do not build broad personal profiles unrelated to investment research.

---

## 17. Security Acceptance Tests

- secret scanner finds no committed secret;
- paper environment has no live credential;
- source prompt injection cannot invoke prohibited tool;
- unauthorized API command is rejected;
- model payload excludes quarantined data;
- direct database role cannot exceed grants;
- forged webhook fails signature or replay check;
- backup is encrypted and restorable;
- security incident activates stand-down;
- audit reconstructs privileged action.
