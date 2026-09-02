import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import LivingWallGalleryStatus from "./LivingWallGalleryStatus";
import { deployedAvailableTruth } from "./livingWallTruthContract.fixture";
import { selectGalleryTruth } from "./TruthSourceAdapter";

test("Gallery renders normalized current factory status, market state, and paper NAV", () => {
  const truth = selectGalleryTruth({
    source: "/living-wall/truth",
    fallback: false,
    data: structuredClone(deployedAvailableTruth),
  });
  const html = renderToStaticMarkup(createElement(LivingWallGalleryStatus, {
    activeRoom: "IDLE",
    truth,
  }));
  assert.match(html, /FACTORY CONDITION<\/span><strong>SANITIZED \/ OBSERVING/);
  assert.match(html, /MARKET VALIDATION<\/span><strong>AVAILABLE/);
  assert.match(html, /PAPER NAV<\/span><strong>\$10,000/);
  assert.match(html, /LIVE EXECUTION<\/span><strong>FALSE/);
});

test("Gallery renders unknown values and degraded status without inventing truth", () => {
  const html = renderToStaticMarkup(createElement(LivingWallGalleryStatus, {
    activeRoom: "FACTORY WATCH",
    truth: {
      degraded: true,
      condition: "DEGRADED / INVESTIGATING",
      marketPhase: "UNKNOWN",
      paperNav: null,
    },
  }));
  assert.match(html, /DEGRADED \/ INVESTIGATING/);
  assert.match(html, /MARKET VALIDATION<\/span><strong>UNKNOWN/);
  assert.match(html, /PAPER NAV<\/span><strong>UNKNOWN/);
});
