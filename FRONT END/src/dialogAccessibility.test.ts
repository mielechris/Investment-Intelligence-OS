import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { activateDialog, dialogTabStops, handleDialogKey, requestDialogClose, type DialogBackground, type DialogDocument, type DialogFocusable, type DialogSurface } from "./dialogAccessibility.ts";

function focusable(name: string, documentTarget: FakeDocument, options: { disabled?: boolean; tabIndex?: number } = {}): DialogFocusable & { name: string; focusCount: number } {
  return {
    name,
    disabled: options.disabled,
    tabIndex: options.tabIndex ?? 0,
    focusCount: 0,
    focus() { this.focusCount += 1; documentTarget.activeElement = this; },
    getAttribute() { return null; },
  };
}

class FakeDocument implements DialogDocument {
  activeElement: unknown = null;
  listener: ((event: KeyboardEvent) => void) | null = null;
  addEventListener(_type: "keydown", listener: (event: KeyboardEvent) => void) { this.listener = listener; }
  removeEventListener(_type: "keydown", listener: (event: KeyboardEvent) => void) { if (this.listener === listener) this.listener = null; }
}

function surface(stops: DialogFocusable[]): DialogSurface & DialogFocusable & { focusCount: number } {
  return {
    tabIndex: -1,
    focusCount: 0,
    focus() { this.focusCount += 1; },
    getAttribute() { return null; },
    contains(target) { return stops.includes(target as DialogFocusable); },
    querySelectorAll() { return stops; },
  };
}

function background(): DialogBackground & { ariaHidden: string | null } {
  return {
    inert: false,
    ariaHidden: null,
    getAttribute(name) { return name === "aria-hidden" ? this.ariaHidden : null; },
    setAttribute(name, value) { if (name === "aria-hidden") this.ariaHidden = value; },
    removeAttribute(name) { if (name === "aria-hidden") this.ariaHidden = null; },
  };
}

function key(keyName: string, shiftKey = false) {
  return { key: keyName, shiftKey, prevented: false, stopped: false, preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; } };
}

test("opening focuses the close control and makes background controls inert", () => {
  const doc = new FakeDocument();
  const opener = focusable("room", doc);
  const closeButton = focusable("close", doc);
  const bg = background();
  const cleanup = activateDialog({ dialog: surface([closeButton]), initialFocus: closeButton, opener, background: [bg], close() {}, documentTarget: doc });
  assert.equal(doc.activeElement, closeButton);
  assert.equal(bg.inert, true);
  assert.equal(bg.ariaHidden, "true");
  cleanup();
});

test("Tab and Shift+Tab wrap within the dialog", () => {
  const doc = new FakeDocument();
  const first = focusable("first", doc);
  const last = focusable("last", doc);
  const dialog = surface([first, last]);
  doc.activeElement = last;
  const forward = key("Tab");
  handleDialogKey(forward, dialog, doc.activeElement, () => {});
  assert.equal(doc.activeElement, first);
  assert.equal(forward.prevented, true);
  const backward = key("Tab", true);
  handleDialogKey(backward, dialog, doc.activeElement, () => {});
  assert.equal(doc.activeElement, last);
  assert.equal(backward.prevented, true);
});

test("Escape requests one close", () => {
  const dialog = surface([]);
  const event = key("Escape");
  let closes = 0;
  handleDialogKey(event, dialog, null, () => { closes += 1; });
  assert.equal(closes, 1);
  assert.equal(event.prevented, true);
  assert.equal(event.stopped, true);
});

test("close-button behavior invokes the supplied close callback", () => {
  let closes = 0;
  requestDialogClose(() => { closes += 1; });
  assert.equal(closes, 1);
});

test("cleanup restores the exact opener and prior background state", () => {
  const doc = new FakeDocument();
  const opener = focusable("room-07", doc);
  const closeButton = focusable("close", doc);
  const bg = background();
  bg.ariaHidden = "false";
  const cleanup = activateDialog({ dialog: surface([closeButton]), initialFocus: closeButton, opener, background: [bg], close() {}, documentTarget: doc });
  cleanup();
  assert.equal(doc.activeElement, opener);
  assert.equal(opener.focusCount, 1);
  assert.equal(bg.inert, false);
  assert.equal(bg.ariaHidden, "false");
  assert.equal(doc.listener, null);
});

test("disabled and negative-tab-index elements are excluded", () => {
  const doc = new FakeDocument();
  const enabled = focusable("enabled", doc);
  const disabled = focusable("disabled", doc, { disabled: true });
  const hidden = focusable("hidden", doc, { tabIndex: -1 });
  assert.deepEqual(dialogTabStops(surface([enabled, disabled, hidden])), [enabled]);
});

test("room dialog markup declares modal title and description relationships", () => {
  const source = readFileSync(new URL("./AuctionFactory.tsx", import.meta.url), "utf8");
  assert.match(source, /role="dialog" aria-modal="true" aria-labelledby=\{titleId\} aria-describedby=\{descriptionId\}/);
  assert.match(source, /<h2 id=\{titleId\}>\{room\.label\}<\/h2><p id=\{descriptionId\}>\{room\.purpose\}<\/p>/);
});
