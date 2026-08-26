export const ACTIVE_CASE_KEY = "iios.activeCaseId";
export const ACTIVE_CASE_EVENT = "iios-active-case-changed";

export function getActiveCaseId(): string | null {
  return window.localStorage.getItem(ACTIVE_CASE_KEY);
}

export function setActiveCaseId(caseId: string | null) {
  if (caseId) window.localStorage.setItem(ACTIVE_CASE_KEY, caseId);
  else window.localStorage.removeItem(ACTIVE_CASE_KEY);
  window.dispatchEvent(new CustomEvent(ACTIVE_CASE_EVENT, { detail: { caseId } }));
}

export function subscribeActiveCase(listener: (caseId: string | null) => void) {
  const notify = () => listener(getActiveCaseId());
  const storage = (event: StorageEvent) => {
    if (event.key === ACTIVE_CASE_KEY) notify();
  };
  window.addEventListener(ACTIVE_CASE_EVENT, notify);
  window.addEventListener("storage", storage);
  return () => {
    window.removeEventListener(ACTIVE_CASE_EVENT, notify);
    window.removeEventListener("storage", storage);
  };
}
