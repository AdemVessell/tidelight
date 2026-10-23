/* Exact three mesh-height terms from scene.py; renderer-independent cross-section. */
(function(root){
'use strict';
function terms(x,y){return [0.060*Math.sin(0.42*x+0.095*y),0.030*Math.sin(0.93*x-0.16*y+1.7),0.015*Math.sin(1.8*x+0.41*y)];}
function height(x,y,enabled=[true,true,true]){return terms(x,y).reduce((s,v,i)=>s+(enabled[i]?v:0),0);}
const api={terms,height};if(typeof module==='object'&&module.exports)module.exports=api;else root.TidelightMath=api;
})(typeof window==='undefined'?globalThis:window);
