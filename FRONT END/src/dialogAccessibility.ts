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
