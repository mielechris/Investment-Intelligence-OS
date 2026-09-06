import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
const source = readFileSync(
  new URL("./AuctionFactory.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(
  new URL("./AuctionEdition.css", import.meta.url),
  "utf8",
);
const registry = readFileSync(
  new URL("./museumPortraitPresentation.ts", import.meta.url),
  "utf8",
);
test("room open resets its own surface and focuses heading without scrolling", () => {
  assert.match(
    source,
    /surfaceRef\.current\?\.scrollTo\(\{ top: 0, left: 0, behavior: "instant" \}\)/,
  );
  assert.match(source, /ref=\{headingRef\} tabIndex=\{-1\}/);
  assert.match(source, /onClick=\{\(event\) => open\(event\.currentTarget\)\}/);
  assert.match(source, /activateDialog\(\{ dialog, initialFocus, opener,/);
  assert.match(source, /\[close, opener, roomId\]/);
});
test("room portraits and quiet evidence stage are intentional", () => {
  assert.match(css, /aspect-ratio:3\/4/);
  assert.match(css, /object-fit:contain;object-position:center center/);
  assert.match(css, /justify-content:center/);
  for (const phrase of [
    "EVIDENCE STAGE QUIET",
    "No authenticated current visual output is available.",
    "The room remains read-only and attentive.",
  ])
    assert.match(source, new RegExp(phrase));
});
test("cast and evidence use separate bounded vertical layers", () => {
  assert.match(
    source,
    /className=\{`auction-room-stage[^`]*`\}[\s\S]*className="auction-room-cinema"[\s\S]*className="auction-evidence-stage"/,
  );
  assert.match(
    css,
    /\.auction-room-stage\{[^}]*flex-direction:column[^}]*overflow:hidden/,
  );
  assert.match(
    css,
    /\.auction-room-stage \.auction-room-cinema article[^}]*margin:0[^}]*transform:none[^}]*overflow:hidden/,
  );
  assert.match(
    css,
    /\.auction-room-stage \.auction-evidence-stage\{[^}]*position:static/,
  );
});
test("single and multi-character casts remain centered and responsive", () => {
  assert.match(css, /flex-wrap:wrap[^}]*justify-content:center/);
  assert.match(css, /flex:0 1 clamp\(150px,18vw,245px\)/);
  assert.match(
    css,
    /\.auction-room-stage \.auction-room-cinema article,\.auction-room-modal:has\(\.auction-evidence-stage\) \.auction-room-stage:not\(\.is-single-cast\) \.auction-room-cinema article\{[^}]*flex:0 0 230px[^}]*max-width:100%/,
  );
  assert.doesNotMatch(css, /\.auction-room-stage[^}]*margin-top:-/);
  assert.doesNotMatch(css, /\.auction-room-stage[^}]*translateY\(-/);
  assert.match(css, /@media\(max-width:520px\)[^{]*\{\.auction-room-stage:not\(\.is-single-cast\) \.auction-room-cinema\{flex:0 0 auto\}/);
});
test("single cast spans and centers within the complete stage grid", () => {
  assert.match(
    source,
    /const singleCast = room\.characterKeys\.length === 1 && room\.guests\.length === 0/,
  );
  assert.match(source, /singleCast \? "is-single-cast" : "is-multi-cast"/);
  assert.match(
    source,
    /className="auction-single-portrait"[^>]*width=\{portrait\.sourceWidth\}[^>]*height=\{portrait\.sourceHeight\}/,
  );
  assert.match(
    css,
    /\.auction-room-stage\.is-single-cast\{[^}]*grid-column:2[^}]*grid-row:1[^}]*grid-template-columns:minmax\(0,1fr\)[^}]*display:grid[^}]*justify-self:stretch[^}]*width:100%[^}]*overflow:visible/,
  );
  assert.match(
    css,
    /\.auction-room-stage\.is-single-cast \.auction-room-cinema\{[^}]*grid-column:1\/-1[^}]*display:flex[^}]*flex-direction:column[^}]*align-items:center[^}]*justify-self:stretch[^}]*width:100%[^}]*max-width:none/,
  );
  assert.match(
    css,
    /\.auction-room-stage\.is-single-cast \.auction-room-cinema article\{[^}]*flex-direction:column[^}]*align-items:center[^}]*width:100%[^}]*max-width:none[^}]*margin:0[^}]*overflow:visible/,
  );
  assert.match(
    css,
    /\.auction-room-stage\.is-single-cast \.auction-single-portrait\{[^}]*display:block[^}]*width:min\(360px,100%\)[^}]*height:auto[^}]*max-width:100%[^}]*margin-inline:auto/,
  );
  assert.doesNotMatch(
    css,
    /auction-single-portrait\{[^}]*(?:aspect-ratio|max-height|object-fit|transform|position:absolute|margin-top:-)/,
  );
  assert.match(
    css,
    /\.auction-room-stage\.is-single-cast \.auction-evidence-stage\{[^}]*grid-column:1\/-1[^}]*justify-self:center[^}]*width:min\(100%,460px\)/,
  );
  assert.match(
    css,
    /is-single-cast\+ \.auction-interior-console\+dl\{[^}]*margin-top:/,
  );
  assert.match(
    css,
    /@media\(max-width:850px\)\{\.auction-room-stage\.is-single-cast\{grid-column:1;grid-row:2\}\}/,
  );
});
test("single-cast registry defaults every character to complete intrinsic final art", () => {
  assert.match(registry, /FINAL_PORTRAITS_V751/);
  assert.match(registry, /sourceWidth: 560/);
  assert.match(registry, /sourceHeight: 700/);
  assert.match(registry, /mode: "intrinsic"/);
  assert.match(registry, /safeInset: 0/);
  assert.match(registry, /maximumRenderedWidth: 360/);
  assert.match(
    source,
    /data-presentation=\{singleCast \? portrait\.mode : "group-card"\}/,
  );
});
test("single cast overrides historical evidence rows and one-third card constraints", () => {
  assert.match(
    css,
    /section:has\(\.auction-room-stage\.is-single-cast\)\{overflow:auto\}/,
  );
  assert.match(
    css,
    /\.auction-room-modal:has\(\.auction-evidence-stage\) \.auction-room-stage\.is-single-cast \.auction-room-cinema\{[^}]*grid-row:auto[^}]*align-self:start[^}]*height:auto/,
  );
  assert.match(
    css,
    /\.auction-room-modal:has\(\.auction-evidence-stage\) \.auction-room-stage\.is-single-cast \.auction-room-cinema article\{[^}]*width:100%[^}]*max-width:none[^}]*height:auto[^}]*aspect-ratio:auto[^}]*overflow:visible/,
  );
  assert.match(
    css,
    /\.auction-room-modal \.auction-room-stage\.is-single-cast \.auction-evidence-stage\{[^}]*grid-row:auto[^}]*position:static[^}]*align-self:start/,
  );
});
