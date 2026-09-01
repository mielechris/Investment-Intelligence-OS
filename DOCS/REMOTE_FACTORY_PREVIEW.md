# Remote Factory Preview

This preview is isolated from the running IIOS paper test.

## Safety boundary

- Source branch: `feature/remote-factory-preview`
- Vercel root directory: `FRONT END`
- The local backend at `127.0.0.1:8002` is not deployed or modified.
- `LIVE_EXECUTION` remains false.
- No broker credentials belong in Vercel.
- Preview telemetry must be read-only and sanitized before connection.

## Deployment sequence

1. Import `mielechris/Investment-Intelligence-OS` into a separate Vercel project.
2. Select `feature/remote-factory-preview` as the preview source.
3. Set the root directory to `FRONT END`.
4. Deploy the static interface without an API environment variable.
5. Verify the interface independently from the Mac runtime.
6. Add `VITE_IIOS_API_URL` only after a read-only telemetry endpoint exists.

The first deployment is deliberately display-only. It cannot start, stop, trade,
reset, or otherwise control the factory running on the Mac.

## Preview checkpoint

The initial Vercel project was created on 2026-09-01. This isolated-branch
checkpoint triggers the first governed preview deployment.
