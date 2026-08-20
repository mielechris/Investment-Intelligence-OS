# Security Implementation

## Immediate Controls

Implement before external integrations:

- `.gitignore`;
- secret loading;
- secret scanner;
- backend auth boundary;
- service identities;
- rights enforcement;
- prompt-injection tests;
- PAPER environment guard.

## API

Use:

- authenticated owner;
- authorization;
- safe errors;
- CORS restriction;
- request validation;
- no secrets in URLs.

## Database

- not publicly exposed by default;
- environment-specific credentials;
- restricted users;
- migration role separated where practical.

## Object Storage

- private;
- no public listing;
- controlled credentials;
- raw immutability/versioning.

## AI

Before model call:

```text
approved provider?
approved model?
approved source rights?
no quarantined data?
no secrets?
minimum necessary context?
```

## Dependencies

Use lock files.

Run:

- dependency scanning;
- secret scanning;
- static checks.

## Incident

Security incident may trigger durable stand-down.
