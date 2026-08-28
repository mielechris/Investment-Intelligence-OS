# Batch 9K Acceptance

Batch 9K is accepted for isolated Mac preview when all of the following hold:

- all Batch 9J regression contracts pass;
- the Batch 9K localhost validation bridge tests pass;
- new Batch 9K React files lint clean;
- the full frontend TypeScript/Vite production build succeeds;
- browser composition contains the live 9E/9G, 9H, 9I and 9J market-operation panels plus the existing Factory Intelligence UI;
- validation bridge remains sidecar-only with no ledger or GitHub credential access;
- preview binds to localhost on port 5176;
- activation fingerprints and preserves the 9G, 9H, 9I and 9J LaunchAgents;
- Backend 8002 and the live IIOS checkout remain unchanged;
- broker connectivity and live execution remain false.

The production browser route is not replaced during Batch 9K preview acceptance. Promotion to the normal IIOS browser entry occurs only after the user visually accepts the isolated preview against live factory behavior.
