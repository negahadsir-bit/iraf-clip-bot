import json, os, subprocess, sys
import numpy as np
from scipy.signal import fftconvolve, butter, sosfilt
SR=44100
rng=np.random.default_rng(7)
def hz(m): return 440*2**((m-69)/12)
def piano(m,dur,vel=0.6):
    n=int(SR*dur); t=np.arange(n)/SR; f=hz(m); y=np.zeros(n)
    for k,a in enumerate([1,.5,.28,.16,.09,.05],1):
        y+=a*np.sin(2*np.pi*f*k*(1+0.0004*k*k)*t)*np.exp(-t*(1.2+0.9*k)*(1.0 if m>55 else .7))
    att=np.minimum(1,t/0.004); y*=att*vel
    return y
def bowed(m,dur,vel=0.5,vib=5.2):
    n=int(SR*dur); t=np.arange(n)/SR; f=hz(m)*(1+0.004*np.sin(2*np.pi*vib*t)*np.minimum(1,t/0.8))
    ph=2*np.pi*np.cumsum(f)/SR
    y=sum(np.sin(ph*k)/k**1.1 for k in range(1,9))
    env=np.minimum(1,t/0.35)*np.minimum(1,(dur-t)/0.5)
    return y*env*vel*0.5
def pad(ms,dur,vel=0.25):
    n=int(SR*dur); t=np.arange(n)/SR; y=np.zeros(n)
    for m in ms:
        for d in (-0.07,0,0.08):
            f=hz(m)*(2**(d/12)); y+=np.sign(np.sin(2*np.pi*f*t+rng.random()*6))*0.0+ (2*((f*t)%1)-1)
    sos=butter(2,900/(SR/2),output='sos'); y=sosfilt(sos,y)
    env=np.minimum(1,t/1.5)*np.minimum(1,(dur-t)/1.5)
    return y*env*vel/ (3*len(ms))*3
def reverb(x,sec=3.2,mix=0.35):
    n=int(SR*sec); t=np.arange(n)/SR
    ir=rng.standard_normal((2,n))*np.exp(-t*2.2)
    sos=butter(1,5000/(SR/2),output='sos'); ir=sosfilt(sos,ir,axis=1)
    wet=np.stack([fftconvolve(x,ir[i])[:len(x)] for i in range(2)])
    wet/=np.abs(wet).max()+1e-9
    dry=np.stack([x,x])
    return dry*(1-mix)+wet*mix*np.abs(x).max()*1.2
def place(buf,y,at):
    i=int(at*SR); j=min(len(buf),i+len(y)); buf[i:j]+=y[:j-i]
def render(name,bpm,chords,arp,mel,bars,melody_voice,seed,outdir='.'):
    beat=60/bpm; bar=4*beat; total=bars*bar+4
    buf=np.zeros(int(SR*total))
    for b in range(bars):
        ch=chords[b%len(chords)]
        t0=b*bar
        place(buf,pad([ch[0]-12]+ch[1:],bar+0.6),t0)
        for i,p in enumerate(arp):
            note=ch[p%len(ch)]+(12 if p>=len(ch) else 0)
            place(buf,piano(note,2.8,0.55 if i%4 else 0.7),t0+i*beat/2)
        place(buf,piano(ch[0]-12,4.0,0.7),t0)
    # sparse melody
    for (bar_i,beat_i,m,d) in mel:
        if bar_i<bars:
            t0=bar_i*bar+beat_i*beat
            y=(bowed(m,d*beat) if melody_voice=='bow' else piano(m,d*beat+1.5,0.8))
            place(buf,y,t0)
    st=reverb(buf)
    st/=np.abs(st).max()+1e-9
    fade=np.minimum(1,np.arange(st.shape[1])/(SR*1.0))*np.minimum(1,(st.shape[1]-np.arange(st.shape[1]))/(SR*3))
    st=st*fade*0.85
    pcm=(st.T*32767).astype('<i2').tobytes()
    raw=os.path.join(outdir,f'{name}.raw'); open(raw,'wb').write(pcm)
    subprocess.run(['ffmpeg','-y','-v','error','-f','s16le','-ar',str(SR),'-ac','2','-i',raw,'-b:a','192k',os.path.join(outdir,f'{name}.mp3')],check=True)
    os.remove(raw)

# ---- presets: mood -> composition (chords are MIDI triads, melody = (bar, beat, note, beats)) ----
def _tri(root, minor=True): return [root, root + (3 if minor else 4), root + 7]
PRESETS = {
 "sad_piano_cello": dict(tags=["غمگین", "احساسی", "پیانو", "آرام"], bpm=68, bars=16, voice="bow",
    chords=[[57,60,64],[53,57,60],[48,52,55],[55,59,62]], arp=[0,1,2,3,2,1,2,1],
    mel=[(0,0,76,3),(0,3,72,1),(1,0,69,4),(2,0,72,2),(2,2,71,2),(3,0,67,4),(4,0,76,3),(4,3,79,1),(5,0,77,4),(6,0,76,2),(6,2,72,2),(7,0,71,3),(7,3,69,1)]),
 "sad_piano_slow": dict(tags=["غمگین", "احساسی", "پیانو", "آرام"], bpm=60, bars=16, voice="piano",
    chords=[[50,53,57],[46,50,53],[53,57,60],[48,52,55]], arp=[0,2,1,2,0,2,1,2],
    mel=[(0,0,81,2),(0,2,77,2),(1,0,74,3),(1,3,77,1),(2,0,76,2),(2,2,72,2),(3,0,69,4),(4,0,81,2),(4,2,84,2),(5,0,82,3),(5,3,81,1),(6,0,79,2),(6,2,77,2),(7,0,76,4)]),
 "epic_dark": dict(tags=["حماسی", "تاریک", "سینمایی"], bpm=84, bars=16, voice="bow",
    chords=[[45,48,52],[41,45,48],[43,47,50],[40,44,47]], arp=[0,0,1,0,2,0,1,0],
    mel=[(0,0,69,4),(1,0,72,4),(2,0,71,2),(2,2,67,2),(3,0,64,4),(4,0,69,2),(4,2,76,2),(5,0,77,4),(6,0,76,2),(6,2,72,2),(7,0,71,4)]),
 "calm_ambient": dict(tags=["آرام", "آمبینت", "امیدوار"], bpm=56, bars=14, voice="piano",
    chords=[[48,52,55],[53,57,60],[45,48,52],[55,59,62]], arp=[0,2,1,2,1,2,0,2],
    mel=[(0,0,79,4),(1,0,76,2),(1,2,72,2),(2,0,76,4),(3,0,74,4),(4,0,79,2),(4,2,84,2),(5,0,81,4),(6,0,76,4),(7,0,72,4)]),
 "romantic_nostalgic": dict(tags=["عاشقانه", "نوستالژیک", "پیانو"], bpm=72, bars=16, voice="piano",
    chords=[[52,56,59],[45,49,52],[47,51,54],[44,47,52]], arp=[0,1,2,1,0,1,2,1],
    mel=[(0,0,76,2),(0,2,80,2),(1,0,81,3),(1,3,80,1),(2,0,78,2),(2,2,76,2),(3,0,75,4),(4,0,76,2),(4,2,83,2),(5,0,81,4),(6,0,80,2),(6,2,78,2),(7,0,76,4)]),
}
MOOD_TO_PRESET = {"غمگین": "sad_piano_cello", "احساسی": "sad_piano_slow", "حماسی": "epic_dark",
                  "آرام": "calm_ambient", "عاشقانه": "romantic_nostalgic", "نوستالژیک": "romantic_nostalgic"}


def compose(preset, outdir, seed=1):
    """Write <preset>.mp3 (original, copyright-free) into outdir and return its catalog row."""
    p = PRESETS[preset]
    render(preset, p["bpm"], p["chords"], p["arp"], p["mel"], p["bars"], p["voice"], seed, outdir)
    mp3 = os.path.join(outdir, preset + ".mp3")
    return dict(id=preset, title=preset, artist="synth (Claude)", file=preset + ".mp3", tags=p["tags"],
                tag_source="synthesized preset", synthesized=True)
