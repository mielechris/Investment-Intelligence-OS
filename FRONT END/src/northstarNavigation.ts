// Presentation-only interaction contracts; no data or operational authority.
export function boundedNavigation(historyTarget: Pick<History, 'pushState'>, currentHash: string, nextHash: string, state: unknown): boolean {
  if (currentHash === nextHash) return true;
  try { historyTarget.pushState(state, '', nextHash); return true; }
  catch { return false; } // No retry, URL fallback, reload or fabricated navigation.
}

export function selectedOpener<T>(id: string | null, rows: readonly { id: string; element: T }[]): T | null {
  if (!id) return null;
  const matches = rows.filter(row => row.id === id);
  return matches.length === 1 ? matches[0].element : null;
}

export function escapeLayer(event: { type?: unknown; key?: unknown; repeat?: unknown; isComposing?: unknown;
  defaultPrevented?: unknown; altKey?: unknown; ctrlKey?: unknown; metaKey?: unknown; shiftKey?: unknown },
  targetInside: boolean, nestedOpen: boolean): 'ignore' | 'disclosure' | 'panel' {
  if (event.type !== 'keydown' || (event.key !== 'Escape' && event.key !== 'Esc') || !targetInside ||
      event.repeat || event.isComposing || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return 'ignore';
  return nestedOpen ? 'disclosure' : 'panel';
}

export function selectionHistoryAction(state: unknown, group: string, id: string, hash: string): 'back' | 'replace' {
  if (!state || typeof state !== 'object' || !('northstarSelection' in state)) return 'replace';
  const entry = state.northstarSelection;
  if (!entry || typeof entry !== 'object') return 'replace';
  const value = entry as Record<string, unknown>;
  return value.group === group && value.id === id && value.hash === hash ? 'back' : 'replace';
}
