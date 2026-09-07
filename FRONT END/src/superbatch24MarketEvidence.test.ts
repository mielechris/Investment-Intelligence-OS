import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = readFileSync(new URL("./MuseumControlRoom.tsx", import.meta.url), "utf8");
const expansion = readFileSync(new URL("./MobExpansionWing.tsx", import.meta.url), "utf8");
const expansionCss = readFileSync(new URL("./MobExpansionWing.css", import.meta.url), "utf8");

test("all governed product truth fields are explicit", () => {
  for (const field of ["Source", "Entitlement", "Last observation", "Freshness", "Completeness", "Current classification", "Forward-only paper research", "Historical adjustment", "Historical-signal methods", "Current snapshot", "Liquidity evidence", "Observed bid/ask", "Paper cost", "Synthetic eligibility", "Operational eligibility", "Corporate-action monitoring", "Credits used", "Evidence fields available", "Missing fields", "Research eligibility", "Paper-research eligibility", "Synthetic activity", "Blocker", "Next scheduled observation"]) assert.match(source, new RegExp(`"${field}"`));
});

test("forward-only qualification never becomes generic paper readiness", () => {
  assert.match(source, /Forward-only paper research/);
  assert.doesNotMatch(source, /"PAPER_TEST_READY"/);
});

test("command center is read-only and cannot consume credits", () => {
  assert.match(source, /browser_credit_authority:false/);
  assert.match(source, /controller_route:false/);
  assert.match(source, /automatic_retry:false/);
  assert.match(source, /Auto-reload<\/dt><dd>DISABLED/);
});

test("missing product evidence remains unavailable", () => {
  assert.match(source, /All rooms remain open and unavailable without authenticated evidence/);
  assert.doesNotMatch(source, /credits_used \?\? 0/);
});

test("human review command layer separates operational and synthetic capital", () => {
  for (const phrase of ["Tuesday Test Day Command Center", "24 × $10,000 independent bases", "Not one $240,000 portfolio", "$10,000 NAV / $10,000 CASH", "WAITING_FOR_CURRENT_TUESDAY_EVIDENCE", "LIQUIDITY PROXY ONLY", "MODELED · NOT OBSERVED", "CONTROLLER DISABLED"])
    assert.match(source, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.equal((source.match(/· (?:U\.S\. LARGE-CAP|BROAD-MARKET|SECTOR|REIT|TREASURY-DURATION|COMMODITY|CURRENCY|LISTED CRYPTO|PREFERRED\/INCOME|ULTRA-SHORT)/g) ?? []).length, 10);
});

test("every pilot interpretation and forward-only lock is human readable", () => {
  for (const phrase of ["U.S. Large-Cap Common Stock", "Broad-Market ETF", "Sector ETF", "Listed REIT ETF Proxy", "Treasury-Duration ETF Proxy", "Commodity ETF Proxy", "Currency ETF Proxy", "Listed Crypto Proxy", "Preferred/Income ETF Proxy", "Ultra-Short ETF Proxy", "Historical-return claim", "Total-return claim", "LIQUIDITY PROXY · NOT ORDER BOOK", "Synthetic readiness", "Operational eligibility"])
    assert.match(source, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});

test("Expansion Wing leads with the Tuesday opening-day command hierarchy", () => {
  for (const phrase of ["TUESDAY PAPER TEST", "10 pilots · 3 observations each · 30-credit maximum", "disabled — awaiting authorization", "Opening Evidence", "Intraday Mark", "Closing Mark", "Browser invocation", "Operational trading"])
    assert.match(expansion, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.ok(expansion.indexOf("TuesdayCommandCenter") < expansion.indexOf("ProductAccountDirectory"));
});

test("all 24 rooms participate through ten pilot, four readiness and ten structural tracks", () => {
  assert.match(expansion, /export const TUESDAY_PILOTS = \[/);
  assert.equal((expansion.match(/ticker: "(?:MU|SPY|XLK|VNQ|TLT|GLD|UUP|IBIT|PFF|BIL)"/g) ?? []).length, 10);
  for (const ticker of ["MU", "SPY", "XLK", "VNQ", "TLT", "GLD", "UUP", "IBIT", "PFF", "BIL"]) assert.match(expansion, new RegExp(`ticker: "${ticker}"`));
  assert.match(expansion, /futureProducts = PRODUCT_DESKS\.filter/);
  assert.match(expansion, /Exactly four listed-equity source-readiness rooms/);
  assert.match(expansion, /Exactly ten specialized structural fail-closed rooms/);
  assert.match(expansion, /24 of 24 product rooms participate/);
  assert.doesNotMatch(expansion, /14 Rooms — Not Available for Tuesday/);
});

test("MU feature, capital separation, and human-first states remain explicit", () => {
  for (const phrase of ["MU · NASDAQ COMMON STOCK", "Tuesday Pilot #1", "Synthetic measuring account: $10,000", "No recommendation", "Operational fund untouched", "Waiting for Tuesday evidence", "SYNTHETIC RESEARCH ACCOUNTS", "OPERATIONAL PAPER FUND", "Not pooled · not deployable · not operational capital", "Exact contract details"])
    assert.match(expansion, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});

test("selection is hash-addressable, focus-restoring, and sticky-header safe", () => {
  for (const contract of ["history.pushState", "hashchange", "scrollIntoView", "detailRef.current?.focus", "Back to Tuesday pilots", "scroll-padding-top", "scroll-margin-block-start", "--mew-sticky-header-height:148px", "--mew-sticky-header-height:220px", "--mew-sticky-header-height:210px"])
    assert.match(`${expansion}\n${expansionCss}`, new RegExp(contract.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.match(expansionCss, /grid-template-columns:minmax\(0,1fr\)/);
  assert.doesNotMatch(expansionCss, /overflow-x:visible/);
});

test("disabled controller commissioning truth is visible without a browser control", () => {
  for (const phrase of ["Monday rehearsal", "September 7, 2026", "Tuesday controller", "<dt>Installed</dt>", "<dt>Running</dt>", "<dt>Activated</dt>", "<dt>Current phase</dt>", "<dt>Human gate</dt>", "controllerInstalled ? \"Yes\" : \"No\"", "controllerRunning ? \"Yes\" : \"No\"", "Corporate-action suspensions", "Synthetic / post-close state", "CONTROLLER_ACTIVATED_", "NO REAL MONEY"])
    assert.match(expansion, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.doesNotMatch(expansion, /Activate Tuesday Controller/);
  assert.doesNotMatch(expansion, /<input[^>]+ticker/i);
});

test("controller presentation is snapshot driven and preserves not-installed truth", () => {
  for (const phrase of ["tuesday_controller_status", "NOT_INSTALLED", "INSTALLATION REQUIRED", "PREPARE DISABLED INSTALLATION", "Restart recovery", "Last sanitized update", "authority_locked"])
    assert.match(expansion, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.doesNotMatch(expansion, /<dd>Yes<\/dd>/);
  assert.doesNotMatch(expansion, /fetch\(|WebSocket|EventSource/);
});

test("governance flow and ten fail-closed conclusions are readable", () => {
  for (const phrase of ["Evidence","Human Review","Committee","Risk","Synthetic Observation","Intraday Mark","Closing Mark","Post-Close Audit","Wrong session","Stale or future evidence","Wrong instrument","Missing candidate lineage","Human decision rejected","Committee rejection","Risk rejection","Budget exhausted","Corporate action unresolved","Unsafe authority"])
    assert.match(expansion, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});

test("controller metadata is semantic, wrapped, and sticky-offset safe", () => {
  for (const phrase of ["mew-controller-status", "<dt>Date</dt>", "<dt>Installed</dt>", "<dt>Activated</dt>", "<dt>Current phase</dt>", "<dt>Human gate</dt>"]) assert.match(expansion, new RegExp(phrase));
  assert.match(expansionCss, /\.mew-controller-status\{display:grid;grid-template-columns:repeat\(2,minmax\(0,1fr\)\);gap:12px/);
  assert.match(expansionCss, /overflow-wrap:anywhere/);
  assert.match(expansionCss, /\.mew-shell \[id\].*scroll-margin-block-start:var\(--mew-anchor-offset\)/);
  assert.match(expansionCss, /html\{scroll-padding-top:var\(--mew-anchor-offset\)\}/);
  assert.match(expansionCss, /--mew-sticky-header-height:220px;--mew-anchor-gap:28px/);
  assert.match(expansionCss, /--mew-sticky-header-height:210px;--mew-anchor-gap:24px/);
});
