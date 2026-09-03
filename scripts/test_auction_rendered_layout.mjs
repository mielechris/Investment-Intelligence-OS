#!/usr/bin/env node

import assert from "node:assert/strict";

const webdriver = new URL(process.env.WEBDRIVER_URL ?? "http://127.0.0.1:4444");
const appUrl = process.env.AUCTION_APP_URL ?? "http://127.0.0.1:4173/";
const browserName = process.env.WEBDRIVER_BROWSER ?? "safari";
const viewports = [[1512, 874], [1916, 1004], [1920, 1080], [2560, 1440], [3840, 2160]];

async function command(path, method = "GET", body) {
  const response = await fetch(new URL(path, webdriver), {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok || payload.value?.error) throw new Error(payload.value?.message ?? `${method} ${path} failed`);
  return payload.value;
}

const session = await command("session", "POST", { capabilities: { alwaysMatch: { browserName } } });
const sessionId = session.sessionId;
const route = (suffix) => `session/${sessionId}/${suffix}`;

async function execute(script, args = []) {
  return command(route("execute/sync"), "POST", { script, args });
}

async function setCssViewport(width, height) {
  const actual = await execute(`
    const width = arguments[0], height = arguments[1], appUrl = arguments[2];
    let frame = document.querySelector('#auction-layout-viewport');
    const ready = frame ? Promise.resolve() : new Promise((resolve, reject) => {
      frame = document.createElement('iframe');
      frame.id = 'auction-layout-viewport';
      frame.src = appUrl;
      frame.onload = resolve;
      frame.onerror = () => reject(new Error('layout viewport failed to load'));
      document.body.replaceChildren(frame);
    });
    frame.style.cssText = 'display:block;border:0;width:' + width + 'px;height:' + height + 'px';
    return ready.then(() => ({width: frame.contentWindow.innerWidth, height: frame.contentWindow.innerHeight, dpr: frame.contentWindow.devicePixelRatio, hostWidth: innerWidth, hostHeight: innerHeight}));
  `, [width, height, appUrl]);
  assert.deepEqual([actual.width, actual.height], [width, height], `CSS viewport must be ${width}x${height}`);
  return actual;
}

const inspectScript = String.raw`
const view = document.querySelector('#auction-layout-viewport')?.contentWindow ?? window;
const targetDocument = view.document;
const {innerWidth, innerHeight, devicePixelRatio} = view;
const getComputedStyle = view.getComputedStyle.bind(view);
const rect = (element) => {
  const box = element.getBoundingClientRect();
  const left = Math.max(0, box.left);
  const top = Math.max(0, box.top);
  const right = Math.min(innerWidth, box.right);
  const bottom = Math.min(innerHeight, box.bottom);
  return {x: box.x, y: box.y, width: box.width, height: box.height, visibleWidth: Math.max(0, right-left), visibleHeight: Math.max(0, bottom-top)};
};
const visible = (element) => {
  const style = getComputedStyle(element);
  const box = rect(element);
  return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) > 0 && box.visibleWidth > 0 && box.visibleHeight > 0;
};
const hit = (element) => {
  const box = element.getBoundingClientRect();
  const points = [[.5,.5],[.25,.25],[.75,.25],[.25,.75],[.75,.75]];
  return points.some(([px,py]) => {
    const x = Math.max(0, Math.min(innerWidth-1, box.left + box.width*px));
    const y = Math.max(0, Math.min(innerHeight-1, box.top + box.height*py));
    const top = targetDocument.elementFromPoint(x,y);
    return top && (element === top || element.contains(top) || top.contains(element));
  });
};
const factory = targetDocument.querySelector('[data-testid="auction-factory"]');
const building = targetDocument.querySelector('[data-testid="auction-building"]');
const max = targetDocument.querySelector('[data-testid="auction-max"]');
const rooms = [...targetDocument.querySelectorAll('[data-testid="auction-room"]')];
const overlays = [...targetDocument.querySelectorAll('[data-testid="quiet-caption"], [data-testid="truth-indicator"], [data-testid="safety-indicator"]')];
const factoryRect = rect(factory);
const area = (box) => box.visibleWidth * box.visibleHeight;
return {
  viewport: {width: innerWidth, height: innerHeight, dpr: devicePixelRatio},
  condition: targetDocument.querySelector('[data-testid="truth-indicator"]')?.innerText ?? "AVAILABLE / CURRENT",
  shellClass: targetDocument.querySelector('.auction-shell').className,
  factory: {...factoryRect, visible: visible(factory), hit: hit(factory)},
  building: {...rect(building), visible: visible(building), hit: hit(building), clipPath: getComputedStyle(building).clipPath, animationName: getComputedStyle(building).animationName},
  max: {...rect(max), visible: visible(max), hit: hit(max)},
  rooms: rooms.map((room) => ({id: room.dataset.roomId, ...rect(room), visible: visible(room), hit: hit(room), state: room.querySelector('small')?.innerText})),
  overlays: overlays.map((overlay) => ({testId: overlay.dataset.testid, ...rect(overlay), pointerEvents: getComputedStyle(overlay).pointerEvents, factoryCoverage: area(rect(overlay))/Math.max(1,area(factoryRect))})),
};`;

function assertLayout(layout, label) {
  assert.equal(layout.factory.visible, true, `${label}: AuctionFactory is computed visible`);
  assert.equal(layout.factory.hit, true, `${label}: AuctionFactory survives viewport hit-testing`);
  assert.equal(layout.building.visible, true, `${label}: architectural cutaway is computed visible`);
  assert.equal(layout.building.hit, true, `${label}: architectural cutaway is not fully occluded`);
  assert.doesNotMatch(layout.building.clipPath, /100%/, `${label}: architecture is not clipped closed`);
  assert.equal(layout.max.visible, true, `${label}: MAX has a visible rectangle`);
  assert.equal(layout.max.hit, true, `${label}: MAX is not fully occluded`);
  assert.equal(layout.rooms.length, 18, `${label}: room registry is complete`);
  for (const room of layout.rooms) {
    assert.equal(room.visible, true, `${label}: ${room.id} has a visible rectangle`);
    assert.equal(room.hit, true, `${label}: ${room.id} is not fully occluded`);
    assert.match(room.state, /UNAVAILABLE|UNKNOWN|LOCKED|IDLE|ACTIVE|DEGRADED/, `${label}: ${room.id} retains an explicit truth state`);
  }
  for (const overlay of layout.overlays) {
    assert.ok(overlay.factoryCoverage < 0.1, `${label}: ${overlay.testId} is environmental, not a canvas replacement`);
  }
}

async function clickText(text) {
  const clicked = await execute("const text=arguments[0]; const view=document.querySelector('#auction-layout-viewport')?.contentWindow ?? window; const button=[...view.document.querySelectorAll('button')].find((item)=>item.textContent.trim()===text); if(!button)return false; button.click(); return true;", [text]);
  assert.equal(clicked, true, `button ${text} exists`);
}

try {
  await command(route("url"), "POST", { url: appUrl });
  const hostViewport = await execute("return {width: innerWidth, height: innerHeight, dpr: devicePixelRatio};");
  const report = [];
  for (const [width, height] of viewports) {
    const viewport = await setCssViewport(width, height);
    const initial = await execute(inspectScript);
    assertLayout(initial, `${width}x${height} Gallery`);

    await clickText("Replay");
    await clickText("Gallery");
    assertLayout(await execute(inspectScript), `${width}x${height} Gallery → Replay → Gallery`);

    await clickText("Wall Art Mode");
    assertLayout(await execute(inspectScript), `${width}x${height} Wall Art Mode`);
    await clickText("Reveal Controls");
    assertLayout(await execute(inspectScript), `${width}x${height} Wall Art exit`);

    await clickText("Pause Scene");
    assertLayout(await execute(inspectScript), `${width}x${height} paused`);
    await clickText("Resume Scene");
    const resumed = await execute(inspectScript);
    assertLayout(resumed, `${width}x${height} resumed`);
    report.push({ viewport, factory: resumed.factory, max: resumed.max, rooms: resumed.rooms });
  }
  console.log(JSON.stringify({ browserName, appUrl, hostViewport, report }, null, 2));
} finally {
  await command(`session/${sessionId}`, "DELETE").catch(() => undefined);
}
