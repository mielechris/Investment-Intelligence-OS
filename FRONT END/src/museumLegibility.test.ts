/// <reference types="node" />
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync(new URL("./MuseumLegibility.css", import.meta.url), "utf8");
const wall = readFileSync(new URL("./LivingWallApp.tsx", import.meta.url), "utf8");
const room = readFileSync(new URL("./AuctionFactory.tsx", import.meta.url), "utf8");

test("seven destinations and six display controls retain readable responsive structure", () => {
  for (const label of ["Gallery", "Story", "Replay", "Command", "Cases", "Expansion Wing", "Factory Watch"]) assert.match(wall, new RegExp(label));
  for (const label of ["Pause Scene", "Wall Art Mode", "Enter Full Screen", "Brightness:", "Collector Plaque", "Sound Muted"]) assert.match(wall, new RegExp(label));
  assert.match(css, /grid-template-areas:"brand destinations" "brand tools"/);
  assert.match(css, /flex-wrap:wrap/);
  assert.match(css, /@media\(max-width:700px\)[\s\S]*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css, /\.auction-tools button:nth-child\(n\)\{display:block\}/);
});

test("normal-flow sticky navigation cannot cover destination content", () => {
  assert.match(css, /\.auction-nav\{position:sticky;top:0/);
  assert.doesNotMatch(css, /\.auction-nav\{[^}]*position:fixed/);
  assert.match(css, /\.auction-scene-plane>main\{min-width:0\}/);
});

test("stale availability notice reserves normal-flow space in every presentation mode", () => {
  assert.match(css, /\.auction-master-1-2 \.auction-degraded,\.auction-master-1-2\.is-wall-mode \.auction-degraded\{[^}]*position:relative[^}]*inset:auto[^}]*width:100%/);
  assert.doesNotMatch(css, /\.auction-master-1-2 \.auction-degraded[^}]*position:fixed/);
  assert.match(css, /\.auction-master-1-2 \.auction-degraded span\{[^}]*overflow-wrap:anywhere/);
});

test("selected Tuesday dossier uses the desktop canvas and stacks responsively", () => {
  assert.match(css, /\.mew-account-detail\{[^}]*width:100%[^}]*max-width:none/);
  assert.match(css, /\.mew-account-detail>\.mew-metrics\{grid-template-columns:repeat\(5,minmax\(0,1fr\)\)\}/);
  assert.match(css, /@media\(max-width:1100px\)[\s\S]*\.mew-account-detail>\.mew-metrics\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)\}/);
  assert.match(css, /@media\(max-width:700px\)[\s\S]*\.mew-account-detail>\.mew-metrics\{grid-template-columns:minmax\(0,1fr\)\}/);
});

test("human conclusions dominate while room machine state remains accessible", () => {
  assert.match(room, /<details className="auction-technical-details">/);
  assert.match(room, /Technical details · exact sanitized machine state/);
  assert.match(css, /\.auction-technical-details summary:focus-visible/);
  assert.match(css, /font-size:clamp\(17px,1\.35vw,21px\)/);
});

test("legibility layer preserves narrow containment and reduced motion", () => {
  assert.match(css, /minmax\(0,1fr\)/);
  assert.match(css, /overflow-wrap:anywhere/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)/);
  assert.doesNotMatch(css, /overflow-x:\s*(?:auto|scroll)/);
});
