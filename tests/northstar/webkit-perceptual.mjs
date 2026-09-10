import assert from 'node:assert/strict';
import bundle from './node_modules/playwright-core/lib/utilsBundle.js';

// Region-specific bounds, not Playwright's global changed-pixel tolerance.
// SSIM uses the mean RGB channel as luminance; separate RGB limits protect color.
export const limits=Object.freeze({imageChannel:32,imageMean:1,imageFraction:.75,
  tileSize:16,tileMean:6,tileSSIM:.95,tileColorBias:2,edgeChannel:4,edgeTileMean:.15,
  edgeTileFraction:.05,maximumDisplacement:.25,displacementImprovement:.1});

export function assertStructure(before,after){
  for(const value of [before,after]){
    assert.equal(value.overflow,0,'OVERFLOW');
    for(const key of ['clipped','overlaps','obstruction','dialog','decoration'])assert.deepEqual(value[key],[],key.toUpperCase());
    assert.equal(value.binding.status,'CURRENT','STALE_BINDING');
    assert(value.text.length&&value.controls.length,'MISSING_CONTENT');
  }
  assert.deepEqual(after,before,'STRUCTURE_CONTENT_STYLE_OR_BINDING_CHANGED');
}
function inside(r,x,y){return x>=r.x&&y>=r.y&&x<r.x+r.width&&y<r.y+r.height;}
function bounds(r,w,h){
  assert(Object.values(r).every(Number.isFinite),'INVALID_REGION');
  const x=Math.max(0,Math.floor(r.x)),y=Math.max(0,Math.floor(r.y));
  const right=Math.min(w,Math.ceil(r.x+r.width)),bottom=Math.min(h,Math.ceil(r.y+r.height));
  return {x,y,width:Math.max(0,right-x),height:Math.max(0,bottom-y)};
}
function edge(a,x,y){
  const i=(y*a.width+x)*4;
  for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
    if(x+dx<0||y+dy<0||x+dx>=a.width||y+dy>=a.height)continue;
    const j=((y+dy)*a.width+x+dx)*4;
    if([0,1,2].some(c=>Math.abs(a.data[i+c]-a.data[j+c])>=16))return true;
  }return false;
}
function shiftedError(a,b,r,dx,dy){
  let sum=0,n=0;
  for(let y=r.y+2;y<r.y+r.height-2;y+=2)for(let x=r.x+2;x<r.x+r.width-2;x+=2){
    const xx=x+dx,yy=y+dy,ix=Math.floor(xx),iy=Math.floor(yy),fx=xx-ix,fy=yy-iy;
    for(let c=0;c<3;c++){
      const v=(1-fx)*(1-fy)*a.data[(iy*a.width+ix)*4+c]+fx*(1-fy)*a.data[(iy*a.width+ix+1)*4+c]+(1-fx)*fy*a.data[((iy+1)*a.width+ix)*4+c]+fx*fy*a.data[((iy+1)*a.width+ix+1)*4+c];
      sum+=Math.abs(v-b.data[(y*a.width+x)*4+c]);n++;
    }
  }return n?sum/n:0;
}
export function compareWebKit(expectedBytes,actualBytes,regions){
  const a=bundle.PNG.sync.read(expectedBytes),b=bundle.PNG.sync.read(actualBytes);
  assert.equal(b.width,a.width,'WIDTH_CHANGED');assert.equal(b.height,a.height,'HEIGHT_CHANGED');
  assert(Array.isArray(regions.images)&&Array.isArray(regions.text),'REGIONS_REQUIRED');
  const images=regions.images.map(r=>bounds(r,a.width,a.height)).filter(r=>r.width&&r.height);
  const text=regions.text.map(r=>bounds(r,a.width,a.height));
  const tileStats=new Map(),imageStats=images.map(r=>({...r,changed:0,sum:0,maximum:0}));
  const diff=new bundle.PNG({width:a.width,height:a.height});
  let changed=0,alpha=0,unclassified=0,edgeMaximum=0;
  let left=a.width,top=a.height,right=-1,bottom=-1;
  const failures=[];
  for(let y=0;y<a.height;y++)for(let x=0;x<a.width;x++){
    const i=(y*a.width+x)*4;let delta=0,sum=0;
    for(let c=0;c<3;c++){const d=Math.abs(a.data[i+c]-b.data[i+c]);delta=Math.max(delta,d);sum+=d;}
    if(a.data[i+3]!==b.data[i+3])alpha++;
    const image=images.findIndex(r=>inside(r,x,y));
    const key=image+':'+Math.floor(x/limits.tileSize)+':'+Math.floor(y/limits.tileSize);
    const t=tileStats.get(key)||{image,n:0,sum:0,changed:0,s1:0,s2:0,s11:0,s22:0,s12:0,bias:[0,0,0]};
    const u=(a.data[i]+a.data[i+1]+a.data[i+2])/3,v=(b.data[i]+b.data[i+1]+b.data[i+2])/3;
    t.n++;t.sum+=sum;t.s1+=u;t.s2+=v;t.s11+=u*u;t.s22+=v*v;t.s12+=u*v;
    for(let c=0;c<3;c++)t.bias[c]+=b.data[i+c]-a.data[i+c];
    if(delta){
      changed++;t.changed++;left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);
      if(image>=0){const s=imageStats[image];s.changed++;s.sum+=sum;s.maximum=Math.max(s.maximum,delta);}
      else{
        edgeMaximum=Math.max(edgeMaximum,delta);
        // Only tiny edge-channel differences in required text/control labels.
        // Backgrounds, shadows, gradients and unexplained regions remain exact.
        if(!text.some(r=>inside(r,x,y))||!edge(a,x,y)||delta>limits.edgeChannel)unclassified++;
      }
    }
    tileStats.set(key,t);
    diff.data.set(delta?[255,0,255,255]:[b.data[i]>>2,b.data[i+1]>>2,b.data[i+2]>>2,255],i);
  }
  let minimumSSIM=1,maximumTileMean=0,maximumColorBias=0,edgeTileMaximum=0;
  for(const t of tileStats.values()){
    if(!t.changed)continue;
    const mean=t.sum/(t.n*3);
    if(t.image>=0){
      const u=t.s1/t.n,v=t.s2/t.n;
      const ssim=((2*u*v+6.5025)*(2*(t.s12/t.n-u*v)+58.5225))/((u*u+v*v+6.5025)*(t.s11/t.n-u*u+t.s22/t.n-v*v+58.5225));
      minimumSSIM=Math.min(minimumSSIM,ssim);maximumTileMean=Math.max(maximumTileMean,mean);
      const bias=Math.max(...t.bias.map(v=>Math.abs(v/t.n)));maximumColorBias=Math.max(maximumColorBias,bias);
      if(bias>limits.tileColorBias)failures.push('IMAGE_LOCAL_COLOR_BIAS');
      if(ssim<limits.tileSSIM||mean>limits.tileMean)failures.push('IMAGE_LOCAL_STRUCTURE_OR_COLOR');
    }else{
      edgeTileMaximum=Math.max(edgeTileMaximum,mean);
      if(mean>limits.edgeTileMean||t.changed/t.n>limits.edgeTileFraction)failures.push('EDGE_REGION_TOO_LARGE');
    }
  }
  for(const r of imageStats){
    r.mean=r.sum/(r.width*r.height*3);r.fraction=r.changed/(r.width*r.height);
    if(r.maximum>limits.imageChannel||r.mean>limits.imageMean||r.fraction>limits.imageFraction)failures.push('IMAGE_MAGNITUDE_OR_REGION');
    const zero=shiftedError(a,b,r,0,0);let best={x:0,y:0,error:zero};
    for(const [dx,dy]of [[.5,0],[-.5,0],[0,.5],[0,-.5],[1,0],[-1,0],[0,1],[0,-1]]){
      const error=shiftedError(a,b,r,dx,dy);if(error<best.error)best={x:dx,y:dy,error};
    }
    r.displacement=best;r.zeroShiftError=zero;
    if(Math.hypot(best.x,best.y)>limits.maximumDisplacement&&zero-best.error>limits.displacementImprovement)failures.push('IMAGE_DISPLACED');
  }
  if(alpha)failures.push('ALPHA_CHANGED');if(unclassified)failures.push('UNAPPROVED_CHANGED_REGION');
  return {ok:!failures.length,failures:[...new Set(failures)],changed,percentage:100*changed/(a.width*a.height),
    bbox:changed?{left,top,right,bottom}:null,alpha,unclassified,edgeMaximum,edgeTileMaximum,minimumSSIM,maximumTileMean,maximumColorBias,
    images:imageStats,diff:bundle.PNG.sync.write(diff)};
}
