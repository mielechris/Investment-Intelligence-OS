import { test as base, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { here } from './prepare.mjs';
import { surfaceFromViewport, decodeImages } from './capture-surface.mjs';
import { assertStructure, compareWebKit, limits } from './webkit-perceptual.mjs';

const contract = JSON.parse(readFileSync(resolve(here, '.build/contract.json')));
const G = contract.geometry;
const widths = [1512, 1020, 386];
const url = '/review/northstar-session.html?fullSession=1';
const phases = Object.keys(contract.fixtures);
const test = base.extend({
  app: async ({ page, context }, use, info) => {
    const errors = [], forbidden = [], requests = [], polls = [];
    let inFlight = 0, maxInFlight = 0, documentEpoch = 0;
    page.on('framenavigated', frame => { if(frame===page.mainFrame())documentEpoch++; });
    let phase = phases[0], status = 200;
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await context.route('**/*', async route => {
      const request = route.request(), parsed = new URL(request.url());
      if (parsed.origin !== 'http://127.0.0.1:5291' || request.method() !== 'GET' ||
          !['/truth-spine/full-session', '/review/fixture-clock.js', ...contract.manifest.outputs.map(row => '/review/' + row.path)].includes(parsed.pathname)) {
        forbidden.push({ method: request.method(), url: request.url() }); await route.abort('blockedbyclient'); return;
      }
      requests.push(parsed.pathname);
      if (parsed.pathname === '/truth-spine/full-session') {
        polls.push({epoch:documentEpoch,at:performance.now()});
        inFlight++; maxInFlight=Math.max(maxInFlight,inFlight);
        try {
          if(status===200)await route.continue();
          else await route.fulfill({status,contentType:'application/json',body:JSON.stringify(contract.fixtures[phase])});
        }
        finally { inFlight--; }
      } else await route.continue();
    });
    async function open(next = phases[0]) {
      phase = next;
      // The fixture server supplies one hash-bound clock wrapper before the
      // unchanged entry module, also usable by the non-blocking native smoke.
      await page.goto(url+'&fixture='+phase);
      await expect(page.locator('[data-shadow-state]')).toHaveAttribute('data-shadow-state', 'CURRENT');
      await stable(page);
    }
    await use({ open, fixture: () => contract.fixtures[phase], requests, errors, unavailable: () => { status = 503; } });
    await info.attach('network-and-runtime', { body: JSON.stringify({ errors, forbidden, requests, polls, maxInFlight, fixture: contract.manifest.fixtureHashes[phase], manifest: contract.manifestHash }), contentType: 'application/json' });
    expect(forbidden, 'No external/permanent/control request permitted').toEqual([]);
    expect(errors, 'No runtime or console errors').toEqual([]);
    expect(maxInFlight, 'One request owner, no concurrent projection polls').toBe(1);
    for(let i=1;i<polls.length;i++)if(polls[i].epoch===polls[i-1].epoch)
      expect(polls[i].at-polls[i-1].at, 'No duplicated polling cadence').toBeGreaterThanOrEqual(4990);
  },
});

async function evaluate(page, body) {
  return page.evaluate('(() => {' + G.TEXT_GEOMETRY + G.OBSTRUCTION_GEOMETRY + G.DIALOG_GEOMETRY + G.DECORATION_GEOMETRY + G.CAPTURE_IDENTITY + G.SETTLEMENT_GEOMETRY + '\nreturn ' + body + ';})()');
}
async function stable(page) {
  // Use the accepted portable core unchanged: two matching adjacent frame pairs,
  // bounded deadline, guarded schedulers, immutable identity and independent cleanup.
  // Only native OS foreground telemetry is intentionally not a CI dependency.
  const result = await page.evaluate(G.SETTLEMENT_GEOMETRY + G.CAPTURE_IDENTITY + `
    (async()=>{
      const decodeImages=${decodeImages.toString()};
      const root=document.querySelector('.northstar-full-session');
      const target=document.activeElement;
      const images=[...root.querySelectorAll('img')].filter(visibleRequiredElement);
      const initial=displayedIdentity().binding;
      let decoded=[];
      const result=await runSettlement({timeoutMs:5000,destination:document.querySelector('.auction-nav nav .is-active')?.textContent.trim()}, {
        now:()=>performance.now(),schedule:fn=>requestAnimationFrame(fn),cancel:id=>cancelAnimationFrame(id),
        timer:(fn,ms)=>setTimeout(fn,ms),clearTimer:id=>clearTimeout(id),
        ready:()=>Promise.all([document.fonts.ready,decodeImages(images).then(value=>{decoded=value})]),
        telemetry:()=>({geometry:geometryFrame(root),identity:{initial,current:displayedIdentity().binding},
          prerequisites:{connected:root.isConnected,focusUnchanged:target===document.activeElement,
            imagesReady:images.every(image=>image.complete&&image.naturalWidth>0)}})
      });
      return {ok:result.ok,reason:result.reason,failure:result.failure,cleanup:result.cleanup,
        frameCount:result.samples.length,matches:result.consecutiveMatches,decoded};
    })()`);
  expect(result, 'Bounded image/frame readiness').toMatchObject({ok:true});
  expect(result.matches).toBeGreaterThanOrEqual(2);
}
async function geometry(page, info, label, dialog = false) {
  await stable(page);
  const data = await evaluate(page, `(()=>{const root=document.querySelector(${JSON.stringify(dialog ? '.northstar-station-dialog' : '.northstar-full-session')});
    const text=requiredText(root),obstruction=obstructionCensus(root),identity=displayedIdentity();
    return {viewport:[innerWidth,innerHeight],overflow:Math.max(0,document.documentElement.scrollWidth-document.documentElement.clientWidth),
      clipped:text.clipped,overlaps:text.overlaps,obstruction:obstruction.violations,identity,
      dialog:${dialog ? 'dialogFailures(dialogMeasurement())' : '[]'},
      decoration:decorationSafety(root).violations};})()`);
  await info.attach(label + '-geometry', { body: JSON.stringify(data), contentType: 'application/json' });
  expect(data.overflow, label).toBe(0);
  expect(data.clipped, label).toEqual([]);
  expect(data.overlaps, label).toEqual([]);
  expect(data.obstruction, label).toEqual([]);
  expect(data.dialog, label).toEqual([]);
  expect(data.decoration, label).toEqual([]);
  expect(data.identity.binding.status).toBe('CURRENT');
  return data;
}
async function accessibility(page, info, selector) {
  const result = await new AxeBuilder({ page }).include(selector).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
  await info.attach('accessibility', { body: JSON.stringify(result), contentType: 'application/json' });
  expect(result.violations).toEqual([]);
}
async function snapshot(page, info, name) {
  await stable(page);
  const before = await evaluate(page, 'displayedIdentity().binding');
  const rectangle = await page.locator('.northstar-station-dialog').boundingBox();
  const structure=async()=>evaluate(page,`(()=>{
    const root=document.querySelector('.northstar-station-dialog'),text=requiredText(root),body=root.querySelector('.northstar-dialog-body'),scrollport=body.getBoundingClientRect();
    const rect=r=>({x:r.x,y:r.y,width:r.width,height:r.height});
    const images=[...root.querySelectorAll('img')].filter(visibleRequiredElement).map(e=>{
      const r=e.getBoundingClientRect(),s=getComputedStyle(e);
      const x=Math.max(r.left,scrollport.left),y=Math.max(r.top,scrollport.top),right=Math.min(r.right,scrollport.right),bottom=Math.min(r.bottom,scrollport.bottom);
      return {src:e.currentSrc,natural:[e.naturalWidth,e.naturalHeight],complete:e.complete,rect:rect(r),paint:{x,y,width:Math.max(0,right-x),height:Math.max(0,bottom-y)},
        style:Object.fromEntries(['display','visibility','opacity','objectFit','objectPosition','transform','filter','imageRendering'].map(k=>[k,s[k]]))};
    });
    return {binding:displayedIdentity().binding,viewport:[innerWidth,innerHeight,devicePixelRatio],overflow:Math.max(0,document.documentElement.scrollWidth-document.documentElement.clientWidth),
      clipped:text.clipped,overlaps:text.overlaps,obstruction:obstructionCensus(root).violations,dialog:dialogFailures(dialogMeasurement()),decoration:decorationSafety(root).violations,
      frame:geometryFrame(root),text:text.text,images,
      controls:[...root.querySelectorAll('button,summary,[tabindex]')].filter(visibleRequiredElement).map(e=>({tag:e.tagName,name:e.getAttribute('aria-label')||e.textContent,disabled:e.disabled===true,rect:rect(e.getBoundingClientRect()),pointerEvents:getComputedStyle(e).pointerEvents})),
      styles:[root,...root.querySelectorAll('*')].filter(visibleRequiredElement).map(e=>({tag:e.tagName,id:e.id,classes:e.className,style:Object.fromEntries(['display','visibility','position','width','height','padding','overflowX','overflowY','fontFamily','fontSize','fontWeight','lineHeight','whiteSpace','transform','filter'].map(k=>[k,getComputedStyle(e)[k]]))}))};
  })()`);
  const layoutBefore=await structure();
  const viewport = await page.screenshot({animations:'disabled',caret:'hide',scale:'css'});
  await info.attach(name+'-full-viewport', {body:viewport,contentType:'image/png'});
  // Regress the semantic surface, not unrelated partially obscured background
  // pixels outside it. Full viewport geometry and screenshots remain evidence.
  // Firefox's element capture can round gradient channels differently from its
  // viewport capture. Use the SAME rasterization boundary as baseline creation.
  // Crop only after capture; no DOM/style mutation, masking or retry.
  // WebKit has region-bound perceptual checks plus an independent exact DOM gate.
  const surface=surfaceFromViewport(viewport,rectangle);
  const layoutAfter=await structure();
  await info.attach(name+'-structural-contract',{body:JSON.stringify({before:layoutBefore,after:layoutAfter}),contentType:'application/json'});
  assertStructure(layoutBefore,layoutAfter);
  if(info.project.name==='webkit'){
    const relative=r=>({x:r.x-rectangle.x,y:r.y-rectangle.y,width:r.width,height:r.height});
    for(const image of layoutBefore.images){
      expect(image.complete).toBe(true);expect(image.natural.every(x=>x>0)).toBe(true);
      const path=new URL(image.src).pathname;
      expect(contract.manifest.outputs.some(row=>'/review/'+row.path===path)).toBe(true);
    }
    const regions={images:layoutBefore.images.map(image=>relative(image.paint)),text:layoutBefore.text.flatMap(t=>t.paintRects.map(r=>relative({x:r.left,y:r.top,width:r.right-r.left,height:r.bottom-r.top})))};
    const expected=readFileSync(resolve(here,'snapshots/darwin/webkit',name+'.png'));
    const {diff,...comparison}=compareWebKit(expected,surface,regions);
    await info.attach(name+'-perceptual-comparison',{body:JSON.stringify({limits,regions,...comparison}),contentType:'application/json'});
    await info.attach(name+'-expected',{body:expected,contentType:'image/png'});
    await info.attach(name+'-observed',{body:surface,contentType:'image/png'});
    await info.attach(name+'-diff',{body:diff,contentType:'image/png'});
    expect(comparison).toMatchObject({ok:true,alpha:0,unclassified:0});
  }else expect(surface).toMatchSnapshot(name + '.png');
  expect(await evaluate(page, 'displayedIdentity().binding')).toEqual(before);
  await info.attach(name + '-binding', { body: JSON.stringify({ before, manifest: contract.manifestHash }), contentType: 'application/json' });
}
async function navigate(page, destination) {
  await page.locator('.auction-nav').getByRole('button', { name: destination, exact: true }).click();
  await expect(page).toHaveURL(/fullSession=1/);
  await stable(page);
}
async function nativeTabTo(page, locator) {
  for (let step = 0; step < 180; step++) {
    if (await locator.evaluate(e => e === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  throw Error('KEYBOARD_TARGET_UNREACHABLE');
}

for (const width of widths) {
  test.describe(`${width}x825`, () => {
    test.use({ viewport: { width, height: 825 } });
    for (const station of contract.stations) {
      test(`station ${station.id} complete dialog contract`, async ({ page, app }, info) => {
        // CI run 34568988612: Firefox Expansion exhausted 180s while all
        // completed readiness checks passed. Trace scroll cadence and complete
        // fixture coverage project at most 310s; 35% headroom rounded up = 420s.
        // Only the overall budget changes: readiness, assertions and retries do not.
        if (info.project.name === 'firefox' && station.id === 'expansion') test.setTimeout(420000);
        await app.open(); await navigate(page, 'Gallery');
        const opener = page.locator(`[data-room-id="${station.id}"]`);
        await expect(opener.locator('.auction-room__identity b')).toHaveText(station.shortLabel);
        await expect(opener).toHaveAttribute('aria-label', new RegExp('^Open ' + station.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ';'));
        await nativeTabTo(page, opener);
        const original = await page.evaluate(() => ({ scroll: [scrollX,scrollY], hash: location.hash, body: document.body.style.cssText, html: document.documentElement.style.cssText }));
        await page.keyboard.press('Enter');
        const dialog = page.locator('.northstar-station-dialog');
        await expect(dialog).toBeVisible();
        await expect(dialog.locator('[id^="auction-room-title-"]')).toBeFocused();
        await geometry(page, info, 'dialog-top', true);
        await snapshot(page, info, `${width}-${station.id}`);
        await accessibility(page, info, '.northstar-station-dialog');
        // Native Tab/Shift+Tab trap, every disclosure (including nested) opened
        // using keyboard activation, never DOM open assignment.
        await page.keyboard.press('Shift+Tab');
        await page.keyboard.press('Tab');
        await expect(dialog.locator('.auction-close')).toBeFocused();
        for (let i = 0; i < 120; i++) {
          await page.keyboard.press('Tab');
          const active = await page.evaluate(() => ({ tag: document.activeElement.tagName, close: document.activeElement.matches('.auction-close'), open: document.activeElement.parentElement.open, inside: !!document.activeElement.closest('.northstar-station-dialog') }));
          expect(active.inside).toBe(true);
          if (active.close) break;
          if (active.tag === 'SUMMARY' && !active.open) await page.keyboard.press('Enter');
          expect(i, 'Bounded disclosure traversal').toBeLessThan(119);
        }
        expect(await dialog.locator('details:not([open])').count()).toBe(0);
        const count = await dialog.locator('button,summary,[tabindex="0"]').count();
        for (const key of ['Tab','Shift+Tab']) for (let i=0;i<count;i++) {
          await page.keyboard.press(key);
          await stable(page);
          const focus = await evaluate(page, `focusMeasurement(document.querySelector('.northstar-station-dialog'))`);
          await info.attach('keyboard-focus', {body:JSON.stringify({key,...focus}),contentType:'application/json'});
          expect(focus.failures).toEqual([]);
        }
        const body = dialog.locator('.northstar-dialog-body');
        const dimensions = await body.evaluate(e => ({ max: e.scrollHeight-e.clientHeight, step: Math.max(20,Math.floor(e.clientHeight*.65)) }));
        const seen = new Set(), total = new Set();
        for (let top=0;;top=Math.min(dimensions.max, top+dimensions.step)) {
          await body.evaluate((e, y) => e.scrollTo({top:y,behavior:'instant'}), top);
          await geometry(page, info, 'scroll-' + top, true);
          const ranges = await evaluate(page, `(()=>{const e=document.querySelector('.northstar-dialog-body'),r=e.getBoundingClientRect();return requiredText(e).text.flatMap((t,i)=>t.rects.map((b,j)=>({id:i+':'+j,visible:b.top>=r.top+2&&b.bottom<=r.bottom-2&&b.left>=r.left&&b.right<=r.right})))})()`);
          for (const row of ranges) { total.add(row.id); if(row.visible)seen.add(row.id); }
          if (top>=dimensions.max)break;
        }
        expect([...total].filter(x=>!seen.has(x)), 'Every expanded text range reachable').toEqual([]);
        await dialog.locator('.auction-close').click(); await expect(dialog).toHaveCount(0); await expect(opener).toBeFocused();
        expect(await page.evaluate(() => ({ scroll: [scrollX,scrollY], hash: location.hash, body: document.body.style.cssText, html: document.documentElement.style.cssText }))).toEqual(original);
        await page.keyboard.press('Space'); await expect(dialog).toBeVisible();
        expect(await body.evaluate(e=>e.scrollTop)).toBe(0);
        await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0); await expect(opener).toBeFocused();
        await page.keyboard.press('Escape'); await expect(opener).toBeFocused();
      });
    }

    test('seven destinations, catalog, history, governance and polling', async ({ page, app }, info) => {
      await app.open(); const fixture=app.fixture();
      const destinations=await page.locator('.auction-nav nav button').allTextContents();
      expect(destinations).toHaveLength(7);
      for(const destination of destinations) { await navigate(page,destination); await geometry(page,info,destination); }
      await navigate(page,'Gallery');
      expect(await page.locator('[data-room-id]').count()).toBe(18);
      const rooms=page.locator('[data-coverage="rooms"] article');await expect(rooms).toHaveCount(24);
      for(const row of fixture.factory.rooms) {
        const card=rooms.filter({has:page.locator(`[data-northstar-opener="${row.id}"]`)});
        await expect(card.locator('h3')).toHaveText(row.name);
        await expect(card).toContainText(row.limitation);
        const button=card.getByRole('button');await button.click();
        await expect(page.locator('#northstar-rooms-heading')).toHaveText(row.name);
        await expect(page.locator('#northstar-rooms-heading')).toBeFocused();
        await page.keyboard.press('Escape');await expect(button).toBeFocused();
      }
      await navigate(page,'Command');
      for(const group of ['agents','governance','subsystems']) {
        await expect(page.locator(`[data-coverage="${group}"] article`)).toHaveCount(fixture.factory[group].length);
        for(const row of fixture.factory[group]) await expect(page.locator(`[data-coverage="${group}"] [data-coverage-id="${row.id}"]`)).toBeVisible();
      }
      await expect(page.locator('[data-coverage="day-trading"]')).toContainText('OBSERVATION_ONLY');
      await expect(page.locator('[data-coverage="day-trading"]')).toContainText(/locked/i);
      await navigate(page,'Cases');
      for(const row of fixture.factory.history) await expect(page.locator('[data-coverage="history"]')).toContainText(row.name);
      const historyButton=page.locator('[data-coverage="history"] button').first();await historyButton.click();
      await expect(page.locator('#northstar-history-heading')).toBeFocused();
      await page.keyboard.press('Escape');await expect(historyButton).toBeFocused();
      await navigate(page,'Gallery');
      await page.getByRole('button',{name:'Collector Plaque',exact:true}).click();
      await expect(page.locator('.northstar-collector-plaque')).toBeVisible();
      await page.keyboard.press('Escape');await expect(page.locator('[data-northstar-plaque-opener]')).toBeFocused();
      const before=await page.evaluate(()=>window.__northstarFixture.responses.length);
      await expect.poll(()=>page.evaluate(()=>window.__northstarFixture.responses.length),{timeout:12000}).toBeGreaterThan(before);
      expect(app.requests.filter(x=>x.startsWith('/truth-spine/')).every(x=>x==='/truth-spine/full-session')).toBe(true);
      await page.reload();await expect(page.locator('[data-shadow-state]')).toHaveAttribute('data-shadow-state','CURRENT');
      await navigate(page,'Story');await navigate(page,'Gallery');await page.goBack();await expect(page).toHaveURL(/#story/);await page.goForward();await expect(page).toHaveURL(/#gallery/);
      await geometry(page,info,'refresh-restoration');
    });
    for(const phase of phases) test(`lifecycle ${phase}`,async({page,app},info)=>{
      await app.open(phase);
      await expect(page.locator('.northstar-session-status [role="status"]')).toContainText(phase);
      expect(Object.values(app.fixture().capabilities).every(x=>x===false)).toBe(true);
      expect(Object.values(app.fixture().counters).every(x=>x===0)).toBe(true);
      await geometry(page,info,'lifecycle-'+phase);
    });
  });
}
