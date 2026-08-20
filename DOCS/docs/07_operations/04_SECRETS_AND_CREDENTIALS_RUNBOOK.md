# Secrets and Credentials Runbook

## Secrets Include

- database passwords;
- API keys;
- model-provider keys;
- market-data credentials;
- object-store keys;
- broker tokens;
- session-signing keys;
- encryption keys.

## Rules

1. Never commit secrets.
2. Never paste secrets into documentation.
3. Never log secrets.
4. Never send secrets to model providers.
5. Use separate environment credentials.
6. Rotate compromised secrets immediately.
7. Paper environment MUST NOT contain live broker credentials.

## Rotation Procedure

1. Activate stand-down if credential affects integrity.
2. Create replacement credential.
3. Update secure runtime store.
4. Restart affected process safely.
5. Verify health.
6. Revoke old credential.
7. Record audit event.
8. Close incident if applicable.

## Accidental Exposure

If a secret is exposed:

- assume compromise;
- rotate;
- remove from source/history where appropriate;
- inspect logs/artifacts;
- record incident.
