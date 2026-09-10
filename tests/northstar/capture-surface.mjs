import assert from 'node:assert/strict';
// Exact Playwright version is locked; use its own PNG implementation so that
// baseline derivation and actual capture share an identical encoding boundary.
import bundle from './node_modules/playwright-core/lib/utilsBundle.js';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
export const portraitContract=JSON.parse(readFileSync(new URL('./portrait-raster-contract.json',import.meta.url)));

export function portraitRasterComparison(name, expectedBytes, actualBytes) {
  const rule=portraitContract.cases[name];
  assert(rule,'UNREVIEWED_PORTRAIT');
  assert.equal(createHash('sha256').update(expectedBytes).digest('hex'),rule.baseline_sha256,'BASELINE_BINDING');
  const expected=bundle.PNG.sync.read(expectedBytes),actual=bundle.PNG.sync.read(actualBytes);
  assert.equal(actual.width,expected.width);assert.equal(actual.height,expected.height);
  let outside=0,alpha=0,changed=0,sum=0,maximum=0;
  const r=rule.pixelRegion;
  for(let p=0;p<actual.width*actual.height;p++){
    const x=p%actual.width,y=Math.floor(p/actual.width),inside=x>=r.x&&x<r.x+r.width&&y>=r.y&&y<r.y+r.height;
    let delta=0;for(let c=0;c<3;c++){const value=Math.abs(actual.data[p*4+c]-expected.data[p*4+c]);delta=Math.max(delta,value);if(inside)sum+=value;}
    if(actual.data[p*4+3]!==expected.data[p*4+3])alpha++;
    if(delta){if(inside)changed++;else outside++;maximum=Math.max(maximum,delta);}
  }
  const mean=sum/(r.width*r.height*3),fraction=changed/(r.width*r.height);
  return {ok:outside===0&&alpha===0&&maximum<=portraitContract.maximumChannelDelta&&mean<=portraitContract.maximumMeanAbsoluteChannelError&&fraction<=portraitContract.maximumChangedImageFraction,
    classification:portraitContract.classification,outside,alpha,changed,maximum,mean,fraction};
}

// Serialized into the browser by the CI adapter; no imports or browser globals.
// The shared settlement core owns the bounded deadline and exactly-once cleanup.
export async function decodeImages(images) {
  return Promise.all(images.map(async image => {
    await image.decode();
    if (!image.complete || image.naturalWidth <= 0 || image.naturalHeight <= 0)
      throw new Error('CI_IMAGE_DECODE_INVALID');
    return { source: image.currentSrc, width: image.naturalWidth, height: image.naturalHeight };
  }));
}

export function surfaceFromViewport(bytes, rectangle) {
  assert(rectangle && Object.values(rectangle).every(Number.isInteger), 'INTEGER_SURFACE_REQUIRED');
  const { x, y, width, height } = rectangle;
  const source = bundle.PNG.sync.read(bytes);
  assert(x >= 0 && y >= 0 && width > 0 && height > 0 &&
    x + width <= source.width && y + height <= source.height, 'SURFACE_OUTSIDE_VIEWPORT');
  const output = new bundle.PNG({ width, height });
  bundle.PNG.bitblt(source, output, x, y, width, height, 0, 0);
  return bundle.PNG.sync.write(output);
}
