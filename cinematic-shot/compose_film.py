#!/usr/bin/env python3
"""Encode the actual 240 Cycles frames and an annotated replay of the same shot.

No interpolation or 2D image warp creates the scene motion. Diagram overlays
are editorial illustrations of the equations; the beauty pixels stay intact.
"""
from pathlib import Path
import argparse, functools, io, json, math, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from matplotlib.mathtext import math_to_image
from matplotlib.font_manager import FontProperties

ROOT=Path(__file__).resolve().parent
W,H,FPS=1600,900,24
COUNT=240
INK=(242,237,222);TEAL=(129,203,200);GOLD=(224,175,132);MUTED=(177,190,193)
FONT='/System/Library/Fonts/Supplemental/Arial.ttf'
SPEC=json.loads((ROOT/'metadata/motion_spec.json').read_text())
CHAPTERS=[
 {'name':'THE SHOT','title':'A world in motion.','subtitle':'Ten seconds. One continuous camera move.','equations':[],
  'detail':'Original procedural scene · Blender Cycles · 240 individually rendered frames'},
 {'name':'01 / MOVING WATER','title':'Give the waves a clock.','subtitle':'Four traveling waves move the actual surface mesh.',
  'equations':[r'\eta(x,y,t)=\sum_{i=1}^{4} A_i\sin(k_{xi}x+k_{yi}y-\omega_i\tau+\phi_i)',r'\omega_i=\sqrt{9.81\,\|\mathbf{k}_i\|},\qquad \tau=0.42t'],
  'detail':'Dispersion-inspired waves with an artistic time scale; fine shader normals drift separately.'},
 {'name':'02 / DRIFTING MIST','title':'Move a field through the light.','subtitle':'The density changes in space and drifts over time.',
  'equations':[r'\mathbf{q}=\operatorname{diag}(0.85,0.85,1.05)\mathbf{g}+t(0.075,0.030,0)',r'D(\mathbf{g},t)=0.028(0.65-0.62g_z)\,R\!\left(N(2.2\mathbf{q})\right)'],
  'detail':'g is Generated space; N is 3D noise (detail 4, roughness 0.66). R(n) = 0.18 + 1.10 clip((n−0.18)/0.60, 0, 1). Procedural advection; no fluid simulation.'},
 {'name':'03 / WET STONE','title':'Let the waterline shape the surface.','subtitle':'Lower stone is smoother and more strongly coated.',
  'equations':[r'u=\operatorname{clip}\!\left(\frac{z+0.3}{1.5},0,1\right)',r'r(z)=0.11+0.47u,\qquad w_{\rm coat}(z)=0.42-0.30u'],
  'detail':'z is world-space height. This authored wetness gradient is applied to the two added foreground stones.'},
 {'name':'04 / THE CAMERA','title':'A smooth path through the inlet.','subtitle':'Foreground stone passes faster than the distant stacks.',
  'equations':[r'p=\operatorname{clip}(t/10,0,1),\qquad s=p^2(3-2p)',r'\mathbf{C}(t)=\left(1.25s,\;-18.5+3s,\;1.42+0.08\sin(\pi p)\right)'],
  'detail':'32.5 mm lens · f/7.1. A moving look-at target keeps the inlet composed. Lengths are scene units.'}
]

@functools.lru_cache(maxsize=None)
def font(size):return ImageFont.truetype(FONT,size)

def formula_image(text,max_width=1080):
    out=io.BytesIO()
    math_to_image('$'+text+'$',out,prop=FontProperties(size=24,math_fontfamily='stix'),dpi=130,format='png',color='black')
    a=np.asarray(Image.open(out).convert('RGBA')).copy()
    a[:,:,3]=255-a[:,:,:3].min(axis=2);a[:,:,:3]=INK
    im=Image.fromarray(a);im=im.crop(im.getbbox())
    if im.width>max_width:im=im.resize((max_width,round(im.height*max_width/im.width)),Image.Resampling.LANCZOS)
    return im

def ease(x):x=max(0,min(1,x));return x*x*(3-2*x)

def draw_diagram(layer,chapter,t):
    d=ImageDraw.Draw(layer)
    x0,y0,x1,y1=1170,690,1545,810
    if chapter==1:
        d.text((x0,y0-31),'SURFACE AT y = 0',font=font(15),fill=TEAL)
        d.line((x0,(y0+y1)/2,x1,(y0+y1)/2),fill=(80,102,108),width=1)
        xs=np.linspace(-12,12,220);height=np.zeros_like(xs)
        for v in SPEC['water']['terms']:
            kx,ky=v['kx_rad_per_m'],v['ky_rad_per_m']
            height+=v['amplitude_m']*np.sin(kx*xs-math.sqrt(9.81*math.hypot(kx,ky))*.42*t+v['phase_rad'])
        points=[(round(x0+i/(len(xs)-1)*(x1-x0)),round((y0+y1)/2-h/.18*50)) for i,h in enumerate(height)]
        d.line(points,fill=INK,width=3)
        d.text((x0,y1+9),'Exact four-wave sum · scene units',font=font(14),fill=MUTED)
    elif chapter==2:
        d.text((x0,y0-31),'DENSITY MODULATION',font=font(15),fill=TEAL)
        d.line((x0,y1,x1,y1),fill=(80,102,108),width=1)
        points=[(round(x0+i/100*(x1-x0)),round(y1-(.18+1.10*max(0,min(1,(i/100-.18)/.60)))/1.28*100)) for i in range(101)]
        d.line(points,fill=GOLD,width=3)
        d.text((x0,y1+9),'R(n) = .18 + 1.10 clip((n−.18)/.60, 0, 1)',font=font(14),fill=MUTED)
    elif chapter==3:
        d.text((x0,y0-31),'ROUGHNESS BY HEIGHT',font=font(15),fill=TEAL)
        for i in range(110):
            value=.11+.47*i/109
            d.line((x0,y1-i,x0+int(value/.58*280),y1-i),fill=tuple(int(a*(.4+.6*i/109)) for a in TEAL),width=1)
        d.text((x0,y1+9),'z = −0.3 → 1.2  /  r = .11 → .58',font=font(14),fill=MUTED)
    elif chapter==4:
        d.text((x0,y0-31),'CAMERA RAIL · TOP VIEW',font=font(15),fill=TEAL)
        start=(x0+35,y1-8);end=(x1-40,y0+12)
        d.line((*start,*end),fill=(80,102,108),width=2)
        s=ease(t/10);p=(start[0]+(end[0]-start[0])*s,start[1]+(end[1]-start[1])*s)
        d.ellipse((p[0]-7,p[1]-7,p[0]+7,p[1]+7),fill=GOLD)
        d.text((x0,y1+9),'1.25 sideways · 3.0 forward',font=font(14),fill=MUTED)

def load_beauty(frame,preview=False):
    path=ROOT/'frames_1600x900'/f'frame_{frame:04d}.png'
    if not path.exists() and preview:
        path=ROOT/'previews'/('benchmark-1600x900-0239.png' if frame>179 else f'sample-{0 if frame<60 else 120:04d}.png')
    im=Image.open(path).convert('RGBA')
    if im.size!=(W,H):
        if not preview:raise ValueError(f'Unexpected source dimensions: {path}: {im.size}')
        im=im.resize((W,H),Image.Resampling.LANCZOS)
    return im

def annotated_frame(index,preview=False):
    chapter=index//COUNT; frame=index%COUNT; t=frame/FPS
    base=load_beauty(frame,preview); spec=CHAPTERS[chapter]
    layer=Image.new('RGBA',(W,H));d=ImageDraw.Draw(layer)
    if chapter==0:
        alpha=int(255*ease(t/.8)*(1-ease((t-3)/1.1)))
        d.text((56,50),'TIDELIGHT',font=font(32),fill=(*INK,alpha))
        d.text((58,96),'A WORLD IN MOTION',font=font(16),fill=(*TEAL,alpha))
        base.alpha_composite(layer);return base.convert('RGB')
    d.rectangle((0,0,W,158),fill=(4,10,15,178))
    d.rectangle((0,610,W,H),fill=(4,10,15,235))
    d.text((54,30),spec['name'],font=font(17),fill=TEAL)
    d.text((54,64),spec['title'],font=font(40),fill=INK)
    d.text((56,119),spec['subtitle'],font=font(20),fill=GOLD)
    d.text((W-222,35),f'REPLAY  /  t = {t:04.1f}s',font=font(16),fill=MUTED)
    row_y=630+(190-sum(im.height for im in spec['images'])-18*(len(spec['images'])-1))/2
    for j,im in enumerate(spec['images']):
        row=im.copy();amount=ease((t-j*.55)/.65)
        row.putalpha(row.getchannel('A').point(lambda a:round(a*amount)))
        layer.alpha_composite(row,(56,round(row_y)))
        row_y+=im.height+18
    draw_diagram(layer,chapter,t)
    # Captions wrap by measured width to avoid clipping the long mist note.
    words=spec['detail'].split();line='';lines=[]
    for word in words:
        trial=(line+' '+word).strip()
        if d.textlength(trial,font=font(16))>1488:lines.append(line);line=word
        else:line=trial
    lines.append(line)
    for j,line in enumerate(lines):d.text((56,841+j*23),line,font=font(16),fill=MUTED)
    d.rectangle((0,H-4,W,H),fill=(32,52,59))
    d.rectangle((0,H-4,round(W*frame/(COUNT-1)),H),fill=TEAL)
    base.alpha_composite(layer);return base.convert('RGB')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stills-only',action='store_true');args=parser.parse_args()
    for chapter in CHAPTERS:chapter['images']=[formula_image(x) for x in chapter['equations']]
    qa=ROOT/'qa';qa.mkdir(exist_ok=True)
    for sec in (2,14,24,34,44):annotated_frame(sec*FPS,preview=args.stills_only).save(qa/f'math-{sec:02d}s.png')
    (ROOT/'metadata/STORYBOARD.json').write_text(json.dumps({'width':W,'height':H,'fps':FPS,'duration_seconds':50,'continuous_shot_seconds':10,'chapters':[{**{k:v for k,v in c.items() if k!='images'},'start':i*10,'end':(i+1)*10} for i,c in enumerate(CHAPTERS)],'disclosure':'Same ten-second 3D-rendered shot replayed for four mathematical explanations. No optical-flow interpolation or image warping.'},indent=2)+'\n')
    if args.stills_only:print('Annotation stills ready');return
    frames=list((ROOT/'frames_1600x900').glob('frame_*.png'));assert len(frames)==COUNT,len(frames)
    ffmpeg='/opt/homebrew/bin/ffmpeg'
    subprocess.run([ffmpeg,'-hide_banner','-loglevel','warning','-y','-framerate',str(FPS),'-start_number','0','-i',str(ROOT/'frames_1600x900/frame_%04d.png'),'-frames:v',str(COUNT),'-an','-c:v','libx264','-threads','4','-preset','slow','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(ROOT/'tidelight-cinematic-shot.mp4')],check=True)
    cmd=[ffmpeg,'-hide_banner','-loglevel','warning','-y','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{W}x{H}','-framerate',str(FPS),'-i','-','-an','-c:v','libx264','-threads','4','-preset','fast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(ROOT/'tidelight-motion-and-math.mp4')]
    with (ROOT/'encode.log').open('w') as log:
        process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=log)
        try:
            for index in range(COUNT*len(CHAPTERS)):
                process.stdin.write(annotated_frame(index).tobytes())
                if index%COUNT==0:print('Encoded chapter',index//COUNT,flush=True)
        finally:process.stdin.close()
        if process.wait():raise RuntimeError('Encoding failed; inspect encode.log')
    print('Clean10s shot and50s math reveal ready',flush=True)

if __name__=='__main__':main()
