(()=>{'use strict';const $=s=>document.querySelector(s),$$=s=>Array.from(document.querySelectorAll(s)),D=window.SHOT_DATA,v=$('#movie');let film='clean',equation=1,selection=0,action=0,readyJob=null;const blobs=new Map();
function showEquation(i){if(equation===i&&$('#equations').childElementCount)return;equation=i;const c=D.storyboard.chapters[i];$('#equation-title').textContent=c.title;$('#equation-note').textContent=c.detail;$('#equations').replaceChildren();for(const f of c.equations){const row=document.createElement('div');katex.render(f,row,{displayMode:true,throwOnError:true,output:'htmlAndMathml'});$('#equations').append(row);}$$('[data-equation]').forEach(b=>b.setAttribute('aria-pressed',String(+b.dataset.equation===i)));}
// Pages serves complete video files. Load a Blob once on an explicit action
// so native controls can seek reliably, without downloading on page arrival.
function fileFor(name){return name==='clean'?'tidelight-cinematic-shot.mp4':'tidelight-motion-and-math.mp4';}
function filmNote(){return film==='clean'?'10 seconds · 1600 × 900 · 24 fps · 240 individually rendered Cycles frames · silent':'50 seconds · the same ten-second shot replayed for four mathematical explanations · silent';}
function selectFilm(name){
  ++selection;++action;readyJob=null;v.pause();film=name;v.src=fileFor(name);v.load();
  $('#download-film').href=fileFor(name);$('#chapters').hidden=name!=='math';
  $('#film-note').textContent=filmNote()+(blobs.has(name)?'':' · loads '+(name==='clean'?'8.4':'23.6')+' MB on play');
  $('#play-film').textContent='Play film ▷';
  $$('[data-film]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.film===name)));setTime(0);
}
async function ensureVideo(){
  if(v.src.startsWith('blob:')&&v.readyState>=1)return true;
  if(readyJob)return readyJob;
  const epoch=selection,name=film;
  $('#film-note').textContent='Loading '+(name==='clean'?'8.4':'23.6')+' MB for smooth playback and seeking…';
  readyJob=(async()=>{
    if(!blobs.has(name)){
      const download=fetch(fileFor(name)).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.blob();}).then(b=>URL.createObjectURL(b)).catch(e=>{blobs.delete(name);throw e;});
      blobs.set(name,download);
    }
    const url=await blobs.get(name);if(epoch!==selection)return false;
    await new Promise((resolve,reject)=>{
      const clean=()=>{v.removeEventListener('loadedmetadata',loaded);v.removeEventListener('error',failed);};
      const loaded=()=>{clean();resolve();};const failed=()=>{clean();reject(Error('Media decode failed'));};
      v.addEventListener('loadedmetadata',loaded);v.addEventListener('error',failed);v.src=url;v.load();
    });
    if(epoch!==selection)return false;$('#film-note').textContent=filmNote();return true;
  })().finally(()=>{if(epoch===selection)readyJob=null;});
  return readyJob;
}
async function activate(t,play){
  const request=++action;
  try{if(!await ensureVideo()||request!==action)return;if(t!==null)v.currentTime=t;if(play)await v.play();}
  catch(e){if(request===action)mediaError();}
}
function seek(t){v.pause();activate(t,false);}
$('#play-film').addEventListener('click',()=>{if(!v.paused){++action;v.pause();}else activate(v.ended?0:null,true);});
v.addEventListener('play',()=>{if(!v.src.startsWith('blob:')){v.pause();activate(null,true);}else $('#play-film').textContent='Pause film Ⅱ';});
v.addEventListener('pause',()=>{$('#play-film').textContent='Play film ▷';});

$$('[data-film]').forEach(b=>b.addEventListener('click',()=>selectFilm(b.dataset.film)));
$$('[data-chapter]').forEach(b=>b.addEventListener('click',()=>{const i=+b.dataset.chapter;seek(i*10+1);if(i)showEquation(i);}));
$$('[data-equation]').forEach(b=>b.addEventListener('click',()=>showEquation(+b.dataset.equation)));
$('#time').addEventListener('input',()=>{const t=+$('#time').value;seek((film==='math'?Math.min(4,Math.floor(v.currentTime/10))*10:0)+t);setTime(t);});
function setTime(t){t=Math.max(0,Math.min(239/24,Math.round(t*24)/24));$('#time').value=t;$('#time-value').textContent=t.toFixed(3)+' s';draw(t);}
function syncFrame(mediaTime){if(v.seeking)return;if(v.paused&&!v.ended&&Math.floor((mediaTime+1e-6)*24)!==Math.floor((v.currentTime+1e-6)*24))return;const atEnd=v.ended||(Number.isFinite(v.duration)&&mediaTime>=v.duration-0.0001);setTime(atEnd?239/24:mediaTime%10);if(film==='math'&&mediaTime>=10)showEquation(Math.min(4,Math.floor(mediaTime/10)));}
v.addEventListener('seeked',()=>syncFrame(v.currentTime));
const hasFrameCallbacks='requestVideoFrameCallback' in v;
v.addEventListener('timeupdate',()=>{if(!hasFrameCallbacks||v.paused||v.ended)syncFrame(Math.floor(v.currentTime*24)/24);});
if(hasFrameCallbacks){const frame=(now,metadata)=>{syncFrame(metadata.mediaTime);v.requestVideoFrameCallback(frame);};v.requestVideoFrameCallback(frame);}
function mediaError(){$('#film-note').textContent='The film could not load. Try Play film again, or use the download link.';}
v.addEventListener('error',mediaError);v.querySelector('source')?.addEventListener('error',mediaError);
const NS='http://www.w3.org/2000/svg';function el(tag,attrs,text){const n=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,x])=>n.setAttribute(k,x));if(text!==undefined)n.textContent=text;return n;}
function draw(t){const on=$$('[data-wave]').map(b=>b.checked),colors=['#dfa483','#81cbc8','#b5a8d5','#6ea8d4'];const g=$('#grid'),c=$('#curves');g.replaceChildren();c.replaceChildren();for(const h of[-.15,0,.15]){const y=140-h/.18*110;g.append(el('line',{x1:48,y1:y,x2:735,y2:y,stroke:'#34464f'}),el('text',{x:39,y:y+4,fill:'#a3b3b9','font-size':11,'text-anchor':'end'},h));}const xs=Array.from({length:300},(_,i)=>-12+24*i/299);const sums=xs.map(()=>0);D.motion.water.terms.forEach((w,j)=>{if(!on[j])return;const k=Math.hypot(w.kx_rad_per_m,w.ky_rad_per_m),ys=xs.map((x,i)=>{const h=w.amplitude_m*Math.sin(w.kx_rad_per_m*x-Math.sqrt(D.motion.water.gravity_m_per_s2*k)*D.motion.water.artistic_time_scale*t+w.phase_rad);sums[i]+=h;return h;});c.append(path(ys,colors[j],1.4));});c.append(path(sums,'#f2eddf',2.7));$('#wave-desc').textContent=on.some(Boolean)?`Four-wave sum at t=${t.toFixed(3)} seconds; ${on.filter(Boolean).length} terms enabled.`:'All terms are off. The surface height is zero.';
function path(ys,color,width){return el('path',{d:ys.map((y,i)=>(i?'L':'M')+(48+687*i/299).toFixed(2)+','+(140-y/.18*110).toFixed(2)).join(' '),fill:'none',stroke:color,'stroke-width':width});}}
$$('[data-wave]').forEach(b=>b.addEventListener('change',()=>draw(+$('#time').value)));$('#reset-waves').addEventListener('click',()=>{$$('[data-wave]').forEach(b=>b.checked=true);draw(+$('#time').value);});showEquation(1);setTime(0);
})();
