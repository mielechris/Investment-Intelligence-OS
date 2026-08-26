const BACKEND_ORIGIN = "http://127.0.0.1:8002";
const PREVIEW_PREFIX = "/__iios_api";
const PREVIEW_PORT = "5189";

type BridgeWindow = typeof window & { __iiosBatch8GPreviewBridge?: boolean };
const bridgeWindow = window as BridgeWindow;
const originalFetch = window.fetch.bind(window);

if (window.location.port === PREVIEW_PORT && !bridgeWindow.__iiosBatch8GPreviewBridge) {
  bridgeWindow.__iiosBatch8GPreviewBridge = true;

  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    if (typeof input === "string" && input.startsWith(BACKEND_ORIGIN)) {
      return originalFetch(`${PREVIEW_PREFIX}${input.slice(BACKEND_ORIGIN.length)}`, init);
    }

    if (input instanceof URL && input.origin === BACKEND_ORIGIN) {
      return originalFetch(`${PREVIEW_PREFIX}${input.pathname}${input.search}${input.hash}`, init);
    }

    if (input instanceof Request && input.url.startsWith(BACKEND_ORIGIN)) {
      const replacement = `${PREVIEW_PREFIX}${input.url.slice(BACKEND_ORIGIN.length)}`;
      return originalFetch(new Request(replacement, input), init);
    }

    return originalFetch(input, init);
  }) as typeof window.fetch;
}
