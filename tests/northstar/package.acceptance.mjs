// Future operational test: intentionally excluded from the fixture *.spec.mjs suite.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import { verifyView, sha, geometryEvaluation } from './package-contract.mjs';

const contract=JSON.parse(fs.readFileSync(process.env.NORTHSTAR_PACKAGE_CONTRACT));
for (const width of [1512,1020,386]) {
  test(`actual historical package ${width}x825`,async({page,context},info)=>{
    await page.setViewportSize({width,height:825});
    const failures=[], responses=[], assets=[], pending=[];
    const allowed=new Set(['/truth-spine/full-session',...contract.outputs.map(r=>'/review/'+r.path)]);
    page.on('pageerror',e=>failures.push(e.message));
    await context.route('**/*',async route=>{
      const r=route.request(),u=new URL(r.url());
      if(u.origin!==contract.origin || r.method()!=='GET' || !allowed.has(u.pathname)){
        failures.push('FORBIDDEN_REQUEST');await route.abort();return;
      }
      await route.continue();
    });
    page.on('response',r=>{
      if(new URL(r.url()).pathname==='/truth-spine/full-session')pending.push((async()=>{
        const bytes=await r.body();const view=JSON.parse(bytes);const binding=verifyView(view,contract);
        responses.push({view,binding,wire_sha256:sha(bytes)});
      })().catch(e=>failures.push(e.message)));
      else pending.push((async()=>{
        const name=new URL(r.url()).pathname.replace(/^\/review\//,'');
        const pin=contract.outputs.find(row=>row.path===name);
        expect(pin,'Unpinned browser asset').toBeTruthy();expect(r.status()).toBe(200);
        const bytes=await r.body();expect(sha(bytes)).toBe(pin.sha256);expect(bytes.length).toBe(pin.bytes);
        assets.push({path:name,sha256:sha(bytes),bytes:bytes.length});
      })().catch(e=>failures.push(e.message)));
    });
    await page.goto('/review/northstar-session.html?fullSession=1');
    await expect(page.locator('[data-package-hash]')).toHaveAttribute('data-package-hash',contract.expected.package_hash);
    await expect(page.getByRole('heading',{name:'Northstar · Historical Replay'})).toBeVisible();
    expect(await page.evaluate(()=>typeof window.__northstarFixture)).toBe('undefined');
    // Reuse the committed geometry algorithms without invoking the fixture runner.
    for(const destination of ['Gallery','Story','Replay','Command','Cases','Expansion Wing','Factory Watch']){
      const button=page.locator('.auction-nav').getByRole('button',{name:destination,exact:true});
      await expect(button).toHaveCount(1);await button.click();
      await Promise.all(pending);
      const current=responses.at(-1);expect(current).toBeTruthy();
      const before=await page.locator('[data-projection-hash]').getAttribute('data-projection-hash');
      const geometry=await page.evaluate(geometryEvaluation(contract.geometry,async ({runSettlement,geometryFrame,requiredText,obstructionCensus,headingTypography},destination)=>{
        const root=document.querySelector('.northstar-full-session');
        const settlement=await runSettlement({destination,timeoutMs:5000},{
          now:()=>window.performance.now(),schedule:fn=>window.requestAnimationFrame(fn),cancel:id=>window.cancelAnimationFrame(id),
          timer:setTimeout,clearTimer:clearTimeout,ready:()=>document.fonts.ready,
          telemetry:()=>({geometry:geometryFrame(root),identity:{package:root.querySelector('[data-package-hash]')?.dataset.packageHash}})});
        return {settlement,frame:geometryFrame(root),text:requiredText(root),obstruction:obstructionCensus(root),headings:headingTypography(root),
          overflow:Math.max(0,document.documentElement.scrollWidth-window.innerWidth)};
      },destination));
      expect(geometry.settlement.ok).toBe(true);expect(geometry.overflow).toBe(0);
      expect(geometry.text.clipped).toEqual([]);expect(geometry.text.overlaps).toEqual([]);
      expect(geometry.obstruction.violations).toEqual([]);
      for(const heading of geometry.headings)expect(heading.lineOverlaps).toEqual([]);
      const screenshot=await page.screenshot({fullPage:true});
      const after=await page.locator('[data-projection-hash]').getAttribute('data-projection-hash');
      expect(after,'Projection changed during capture').toBe(before);
      expect(await page.evaluate(geometryEvaluation(contract.geometry,({geometryFrame})=>geometryFrame(document.querySelector('.northstar-full-session'))))).toEqual(geometry.frame);
      expect(responses.some(r=>r.binding.projection_hash===before)).toBe(true);
      await info.attach(destination+'-capture',{body:screenshot,contentType:'image/png'});
      await info.attach(destination+'-binding',{body:JSON.stringify({before,after,geometry,contract:contract.content_hash}),contentType:'application/json'});
    }
    await Promise.all(pending);
    expect(failures).toEqual([]);expect(responses.length).toBeGreaterThan(0);
    const view=responses.at(-1).view;
    expect(view.factory.rooms).toHaveLength(24);expect(view.factory.agents).toHaveLength(8);
    expect(view.factory.day_trading.order_allowance).toBe(0);
    await info.attach('package-responses',{body:JSON.stringify(responses),contentType:'application/json'});
    await info.attach('package-assets',{body:JSON.stringify(assets),contentType:'application/json'});
  });
}
