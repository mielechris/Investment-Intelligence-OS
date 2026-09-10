export const DIALOG_FOCUSABLE_SELECTOR = "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";

export interface DialogFocusable {
  disabled?: boolean;
  tabIndex: number;
  focus(options?: FocusOptions): void;
  getAttribute(name: string): string | null;
}

export interface DialogSurface extends DialogFocusable {
  contains(target: unknown): boolean;
  querySelectorAll(selector: string): ArrayLike<DialogFocusable>;
}

export interface DialogBackground {
  inert: boolean;
  getAttribute(name: string): string | null;
  setAttribute(name: string, value: string): void;
  removeAttribute(name: string): void;
}

export interface DialogDocument {
  activeElement: unknown;
  addEventListener(type: "keydown", listener: (event: KeyboardEvent) => void, capture: boolean): void;
  removeEventListener(type: "keydown", listener: (event: KeyboardEvent) => void, capture: boolean): void;
}

export function dialogTabStops(dialog: DialogSurface): DialogFocusable[] {
  return Array.from(dialog.querySelectorAll(DIALOG_FOCUSABLE_SELECTOR)).filter((element) =>
    !element.disabled && element.tabIndex >= 0 && element.getAttribute("aria-hidden") !== "true"
  );
}

export function requestDialogClose(close: () => void): void {
  close();
}

export function handleDialogKey(event: Pick<KeyboardEvent, "key" | "shiftKey" | "preventDefault" | "stopPropagation">, dialog: DialogSurface, activeElement: unknown, close: () => void): void {
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    requestDialogClose(close);
    return;
  }
  if (event.key !== "Tab") return;
  const stops = dialogTabStops(dialog);
  if (!stops.length) {
    event.preventDefault();
    dialog.focus({ preventScroll: true });
    return;
  }
  const first = stops[0];
  const last = stops[stops.length - 1];
  if (event.shiftKey && (activeElement === first || !dialog.contains(activeElement))) {
    event.preventDefault();
    last.focus({ preventScroll: true });
  } else if (!event.shiftKey && (activeElement === last || !dialog.contains(activeElement))) {
    event.preventDefault();
    first.focus({ preventScroll: true });
  }
}

export function activateDialog({ dialog, initialFocus, opener, background, close, documentTarget }: {
  dialog: DialogSurface;
  initialFocus: DialogFocusable;
  opener: DialogFocusable | null;
  background: DialogBackground[];
  close: () => void;
  documentTarget: DialogDocument;
}): () => void {
  const prior = background.map((element) => ({
    element,
    inert: element.inert,
    ariaHidden: element.getAttribute("aria-hidden"),
  }));
  for (const element of background) {
    element.inert = true;
    element.setAttribute("aria-hidden", "true");
  }
  const onKeyDown = (event: KeyboardEvent) => handleDialogKey(event, dialog, documentTarget.activeElement, close);
  documentTarget.addEventListener("keydown", onKeyDown, true);
  initialFocus.focus({ preventScroll: true });

  return () => {
    documentTarget.removeEventListener("keydown", onKeyDown, true);
    for (const state of prior) {
      state.element.inert = state.inert;
      if (state.ariaHidden === null) state.element.removeAttribute("aria-hidden");
      else state.element.setAttribute("aria-hidden", state.ariaHidden);
    }
    opener?.focus({ preventScroll: true });
  };
}

// Northstar-only modal ownership. Legacy consumers retain activateDialog above.
// One document lock is shared by nested owned layers and restored byte-for-byte.
const northstarModalOwners = /* @__PURE__ */ new WeakMap<Document, { layers: symbol[]; unlock: () => void }>();

export function activateNorthstarDialog({ dialog, initialFocus, opener, background, close, documentTarget }: {
  dialog: HTMLElement; initialFocus: HTMLElement; opener: HTMLElement | null;
  background: HTMLElement[]; close: () => void; documentTarget: Document;
}): () => void {
  const win = documentTarget.defaultView;
  if (!win) throw new Error('DIALOG_WINDOW_UNAVAILABLE');
  let owner = northstarModalOwners.get(documentTarget);
  if (!owner) {
    const x = win.scrollX, y = win.scrollY;
    const changes: [HTMLElement, string, string][] = [
      [documentTarget.body, 'position', 'fixed'], [documentTarget.body, 'top', `${-y}px`],
      [documentTarget.body, 'left', `${-x}px`], [documentTarget.body, 'right', '0'], [documentTarget.body, 'width', 'auto'],
      [documentTarget.body, 'overflow', 'hidden'], [documentTarget.documentElement, 'overflow', 'hidden'],
      [documentTarget.documentElement, 'scroll-behavior', 'auto'],
    ];
    const saved = changes.map(([element, property]) => ({ element, property,
      value: element.style.getPropertyValue(property), priority: element.style.getPropertyPriority(property) }));
    changes.forEach(([element, property, value]) => element.style.setProperty(property, value));
    owner = { layers: [], unlock: () => {
      for (const { element, property, value, priority } of saved) {
        if (value) element.style.setProperty(property, value, priority);
        else element.style.removeProperty(property);
      }
      win.scrollTo({ left: x, top: y, behavior: 'instant' });
    } };
    northstarModalOwners.set(documentTarget, owner);
  }
  const token = Symbol('northstar-modal'); owner.layers.push(token);
  const topmost = () => owner.layers.at(-1) === token;
  const prior = background.map(element => ({ element, inert: element.inert, hidden: element.getAttribute('aria-hidden') }));
  prior.forEach(({ element }) => { element.inert = true; element.setAttribute('aria-hidden', 'true'); });
  let closing = false, disposed = false;
  const stops = () => [...dialog.querySelectorAll<HTMLElement>(DIALOG_FOCUSABLE_SELECTOR + ', summary')].filter(e => {
    if (e.tabIndex < 0 || e.closest('[hidden],[inert],[aria-hidden="true"]') || !e.getClientRects().length) return false;
    const style = win.getComputedStyle(e);
    if (style.display === 'none' || style.visibility !== 'visible') return false;
    for (let p = e.parentElement; p && p !== dialog; p = p.parentElement) {
      if (p.tagName === 'DETAILS' && !(p as HTMLDetailsElement).open && !p.querySelector('summary')?.contains(e)) return false;
    }
    return true;
  });
  const onKey = (event: KeyboardEvent) => {
    if (!topmost() || closing || event.defaultPrevented || event.isComposing || event.repeat) return;
    if (event.key === 'Escape') {
      event.preventDefault(); event.stopImmediatePropagation(); closing = true; close(); return;
    }
    if (event.key !== 'Tab' || event.ctrlKey || event.metaKey || event.altKey) return;
    const list = stops(), active = documentTarget.activeElement;
    if (!list.length) { event.preventDefault(); initialFocus.focus({ preventScroll: true }); return; }
    const index = list.findIndex(e => e === active);
    // Own the complete tab cycle, not only its boundary: Safari's platform tab
    // preference must not skip buttons or disclosure summaries in this modal.
    // Focus scrolls only the owned body; scroll padding/margins retain its ring.
    const next = index < 0 ? (event.shiftKey ? list.length - 1 : 0)
      : (index + (event.shiftKey ? -1 : 1) + list.length) % list.length;
    event.preventDefault(); list[next].focus();
  };
  const onFocus = () => { if (topmost() && !closing && !dialog.contains(documentTarget.activeElement)) initialFocus.focus({ preventScroll: true }); };
  documentTarget.addEventListener('keydown', onKey, true);
  documentTarget.addEventListener('focusin', onFocus, true);
  initialFocus.focus({ preventScroll: true });
  return () => {
    if (disposed) return; disposed = true;
    documentTarget.removeEventListener('keydown', onKey, true);
    documentTarget.removeEventListener('focusin', onFocus, true);
    owner.layers.splice(owner.layers.indexOf(token), 1);
    for (const { element, inert, hidden } of prior) {
      element.inert = inert;
      if (hidden === null) element.removeAttribute('aria-hidden'); else element.setAttribute('aria-hidden', hidden);
    }
    if (!owner.layers.length) { owner.unlock(); northstarModalOwners.delete(documentTarget); }
    // Restoration is an explicit accessibility event, not inferred keyboard
    // input. Show its scoped indicator until blur or a real pointer interaction.
    if (opener?.getAttribute('data-room-id')) {
      const clear = () => {
        opener.removeAttribute('data-northstar-restored-focus');
        opener.removeEventListener('blur', clear);
        opener.removeEventListener('pointerdown', clear);
      };
      opener.setAttribute('data-northstar-restored-focus', '');
      opener.addEventListener('blur', clear, { once: true });
      opener.addEventListener('pointerdown', clear, { once: true });
    }
    opener?.focus({ preventScroll: true });
  };
}
