import json, os, subprocess, sys
import numpy as np
from scipy.signal import fftconvolve, butter, sosfilt
SR=44100
rng=np.random.default_rng(7)
def hz(m): return 440*2**((m-69)/12)
def piano(m,dur,vel=0.6):
    n=int(SR*dur); t=np.arange(n)/SR; f=hz(m); y=np.zeros(n)
    low=1.0 if m>55 else .7
    for k,a in enumerate([1,.55,.35,.2,.13,.08,.05,.03],1):
        y+=a*np.sin(2*np.pi*f*k*(1+0.0004*k*k)*t)*np.exp(-t*(1.1+0.8*k)*low)
    y*=np.minimum(1,t/0.004)
    h=int(SR*0.012); click=sosfilt(butter(2,[500/(SR/2),4000/(SR/2)],btype='band',output='sos'),rng.standard_normal(h))
    y[:h]+=click*np.exp(-np.arange(h)/SR/0.004)*0.25  # hammer
    return sosfilt(butter(1,5500/(SR/2),output='sos'),y)*vel
def bowed(m,dur,vel=0.5,vib=5.2):
    n=int(SR*dur); t=np.arange(n)/SR; f=hz(m)*(1+0.004*np.sin(2*np.pi*vib*t)*np.minimum(1,t/0.8))
    ph=2*np.pi*np.cumsum(f)/SR
    y=sum(np.sin(ph*k)/k**1.1 for k in range(1,9))
    env=np.minimum(1,t/0.35)*np.minimum(1,(dur-t)/0.5)
    return y*env*vel*0.5
def strings(m,dur,vel=0.4,vib=5.3,voices=3,attack=0.5):
    """A small string section: a few detuned bowed voices, each with its own vibrato, bow noise, warm top."""
    n=int(SR*dur); t=np.arange(n)/SR; y=np.zeros(n)
    for v in range(voices):
        det=(v-(voices-1)/2)*9  # cents
        f=hz(m)*2**(det/1200)*(1+0.0035*np.sin(2*np.pi*(vib+0.17*v)*t+rng.random()*6)*np.minimum(1,t/0.9))
        ph=2*np.pi*np.cumsum(f)/SR
        y+=sum(np.sin(ph*k)/k**1.15 for k in range(1,7))
    env=np.minimum(1,t/attack)*np.minimum(1,np.maximum(0,(dur-t))/0.6)
    bow=sosfilt(butter(2,[2000/(SR/2),6000/(SR/2)],btype='band',output='sos'),rng.standard_normal(n))*0.012
    y=sosfilt(butter(2,3400/(SR/2),output='sos'),y/voices*0.5+bow)
    return y*env*vel
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

# ---- percussion: synthesized kit, so every bed can have a pulse ----
def _env(n, tau): return np.exp(-np.arange(n) / SR / tau)
def kick(vel=1.0):
    n = int(SR * 0.45); t = np.arange(n) / SR
    f = 45 + 95 * np.exp(-t * 28)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.12)
    y[:60] += np.linspace(0.6, 0, 60)  # click
    return y * vel
def taiko(vel=1.0):
    n = int(SR * 1.0); t = np.arange(n) / SR
    f = 52 + 38 * np.exp(-t * 14)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.32)
    y += 0.35 * rng.standard_normal(n) * _env(n, 0.02)
    sos = butter(2, 700 / (SR / 2), output='sos')
    return sosfilt(sos, y) * vel * 1.4
def snare(vel=1.0, deep=False):
    n = int(SR * 0.28); t = np.arange(n) / SR
    noise = sosfilt(butter(2, [200 / (SR / 2), 7000 / (SR / 2)], btype='band', output='sos'), rng.standard_normal(n))
    y = noise * _env(n, 0.09) * 0.7 + np.sin(2 * np.pi * (150 if deep else 200) * t) * _env(n, 0.07) * 0.6
    return y * vel
def clap(vel=1.0):
    n = int(SR * 0.3); y = np.zeros(n)
    noise = sosfilt(butter(2, [700 / (SR / 2), 5000 / (SR / 2)], btype='band', output='sos'), rng.standard_normal(n))
    for d in (0, 0.012, 0.024):
        i = int(SR * d); y[i:] += noise[:n - i] * _env(n - i, 0.012 if d < 0.024 else 0.11)
    return y * vel * 0.5
def hat(vel=1.0, open_=False):
    n = int(SR * (0.22 if open_ else 0.06))
    noise = sosfilt(butter(2, 7000 / (SR / 2), btype='high', output='sos'), rng.standard_normal(n))
    return noise * _env(n, 0.07 if open_ else 0.018) * vel * 0.35
def swell(dur, vel=0.5):
    n = int(SR * dur); t = np.arange(n) / SR
    noise = sosfilt(butter(2, [3000 / (SR / 2), 9000 / (SR / 2)], btype='band', output='sos'), rng.standard_normal(n))
    return noise * (t / dur) ** 2 * vel * 0.6

# 16 steps per bar: {voice: [steps]}
DRUM_STYLES = {
 "drive":  dict(kick=[0, 6, 8, 14], snare=[4, 12], hat=list(range(0, 16, 2)), clap=[12]),
 "pulse":  dict(kick=[0, 4, 8, 12], snare=[], hat=[2, 6, 10, 14], clap=[4, 12]),
 "epic":   dict(taiko=[0, 3, 6, 8, 11, 14], snare=[4, 12], hat=[]),
 "sorrow": dict(kick=[0, 10], snare=[8], hat=[4, 12], clap=[]),
}
def drums_track(buf, bars, bpm, style):
    beat = 60 / bpm; bar = 4 * beat; step = beat / 4
    pat = DRUM_STYLES[style]
    for b in range(bars):
        build = 0.75 + 0.25 * min(1.0, (b % 8) / 7)  # grows through each 8-bar phrase
        for name, steps in pat.items():
            for st in steps:
                at = b * bar + st * step + (step * 0.12 if name in ('hat', 'clap') and st % 4 == 2 else 0)
                acc = 1.0 if st % 4 == 0 else 0.75
                if name == 'kick': y = kick(0.9 * build * acc)
                elif name == 'taiko': y = taiko(0.85 * build * acc)
                elif name == 'snare': y = snare(0.2 * build, deep=(style in ('epic', 'sorrow')))
                elif name == 'clap': y = clap(0.3 * build)
                else: y = hat(0.8 * acc * build)
                place(buf, y, at)
        if style == 'epic' and b % 8 == 7:
            place(buf, swell(bar), b * bar)  # riser into the next phrase

def _mix2(a,b):
    n=max(len(a),len(b)); y=np.zeros(n); y[:len(a)]+=a; y[:len(b)]+=b
    return y
def render(name,bpm,chords,arp,mel,bars,melody_voice,seed,outdir='.',drums=None,arp_step=0.5,mel_period=8):
    beat=60/bpm; bar=4*beat; total=bars*bar+4
    buf=np.zeros(int(SR*total))
    for b in range(bars):
        ch=chords[b%len(chords)]
        t0=b*bar
        for ci,cn in enumerate([ch[0]-12]+ch[1:]+[ch[0]+12]):
            place(buf,strings(cn,bar+0.8,0.5 if ci==0 else 0.3,voices=2 if ci==0 else 3),t0)
        for i in range(int(round(4/arp_step))):
            p=arp[i%len(arp)]
            note=ch[p%len(ch)]+(12 if p>=len(ch) else 0)
            place(buf,piano(note,2.8 if arp_step>=0.5 else 1.6,0.55 if i%4 else 0.7),t0+i*beat*arp_step)
        place(buf,piano(ch[0]-12,4.0,0.7),t0)
    # sparse melody
    for rep in range(0,bars,mel_period):
        for (bar_i,beat_i,m,d) in mel:
            if rep+bar_i<bars:
                t0=(rep+bar_i)*bar+beat_i*beat
                y=(strings(m,d*beat+0.4,0.7,voices=2,attack=0.25) if melody_voice=='bow' else _mix2(piano(m,d*beat+1.5,0.8),strings(m,d*beat+0.4,0.25,voices=2,attack=0.25)))
                place(buf,y,t0)
    st=reverb(buf)
    st/=np.abs(st).max()+1e-9
    if drums:  # percussion stays dry and tight; only the harmony sits in the reverb
        dr=np.zeros(len(buf)); drums_track(dr,bars,bpm,drums)
        dr/=np.abs(dr).max()+1e-9
        st=st*0.8+np.stack([dr,dr])*0.7
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
 # ---- faster, more emotional beds with a pulse (these are the defaults) ----
 "emotional_drive": dict(tags=["احساسی", "ریتمیک", "هیجانی", "امیدوار"], bpm=100, bars=28, voice="bow", drums="drive", arp_step=0.25,
    chords=[[57,60,64],[53,57,60],[48,52,55],[55,59,62]], arp=[0,1,2,1],
    mel=[(0,0,76,3),(0,3,72,1),(1,0,69,3),(1,3,72,1),(2,0,72,2),(2,2,76,2),(3,0,74,3),(3,3,71,1),(4,0,76,2),(4,2,79,2),(5,0,77,3),(5,3,76,1),(6,0,76,2),(6,2,72,2),(7,0,71,4)]),
 "epic_percussive": dict(tags=["حماسی", "هیجانی", "ریتمیک", "انگیزشی"], bpm=108, bars=28, voice="bow", drums="epic", arp_step=0.5,
    chords=[[45,48,52],[41,45,48],[43,47,50],[40,44,47]], arp=[0,0,1,0,2,0,1,0],
    mel=[(0,0,69,4),(1,0,72,4),(2,0,71,2),(2,2,67,2),(3,0,64,4),(4,0,69,2),(4,2,76,2),(5,0,77,4),(6,0,76,2),(6,2,72,2),(7,0,71,4)]),
 "sorrowful_pulse": dict(tags=["سوزناک", "غمگین", "احساسی"], bpm=92, bars=24, voice="bow", drums="sorrow", arp_step=0.5,
    chords=[[57,60,64],[53,57,60],[50,53,57],[52,56,59]], arp=[0,1,2,1,2,1,2,1],
    mel=[(0,0,76,3),(0,3,75,1),(1,0,72,4),(2,0,74,2),(2,2,72,2),(3,0,71,4),(4,0,76,2),(4,2,81,2),(5,0,79,3),(5,3,77,1),(6,0,76,2),(6,2,74,2),(7,0,72,4)]),
 # ---- piano-led beds (with a string section underneath) ----
 "piano_emotional": dict(tags=["احساسی", "غمگین", "پیانو"], bpm=96, bars=26, voice="piano", drums="sorrow", arp_step=0.5,
    chords=[[57,60,64],[55,59,62],[53,57,60],[52,56,59]], arp=[0,1,2,1,2,1,2,1],
    mel=[(0,0,81,2),(0,2,79,1),(0,3,76,1),(1,0,79,3),(1,3,76,1),(2,0,77,2),(2,2,76,2),(3,0,76,3),(3,3,80,1),(4,0,81,2),(4,2,84,2),(5,0,83,3),(5,3,79,1),(6,0,81,2),(6,2,77,2),(7,0,76,4)]),
 "piano_hope": dict(tags=["امیدوار", "پیانو", "احساسی", "ریتمیک"], bpm=104, bars=28, voice="piano", drums="drive", arp_step=0.5,
    chords=[[60,64,67],[55,59,62],[57,60,64],[53,57,60]], arp=[0,1,2,1,2,1,2,1],
    mel=[(0,0,76,2),(0,2,79,2),(1,0,78,3),(1,3,76,1),(2,0,76,2),(2,2,72,2),(3,0,72,3),(3,3,74,1),(4,0,76,2),(4,2,84,2),(5,0,83,3),(5,3,79,1),(6,0,81,2),(6,2,77,2),(7,0,76,4)]),
 "tense_pulse": dict(tags=["هیجانی", "ریتمیک"], bpm=120, bars=32, voice="bow", drums="pulse", arp_step=0.25,
    chords=[[50,53,57],[46,50,53],[43,46,50],[45,49,52]], arp=[0,1,2,1],
    mel=[(0,0,74,2),(0,2,77,2),(1,0,76,3),(1,3,74,1),(2,0,72,2),(2,2,74,2),(3,0,70,4),(4,0,74,2),(4,2,81,2),(5,0,79,3),(5,3,77,1),(6,0,76,2),(6,2,74,2),(7,0,69,4)]),
 # ---- gentler beds, kept for calm speech ----
 "calm_ambient": dict(tags=["آرام", "آمبینت", "امیدوار"], bpm=72, bars=22, voice="piano", drums=None,
    chords=[[48,52,55],[53,57,60],[45,48,52],[55,59,62]], arp=[0,2,1,2,1,2,0,2],
    mel=[(0,0,79,4),(1,0,76,2),(1,2,72,2),(2,0,76,4),(3,0,74,4),(4,0,79,2),(4,2,84,2),(5,0,81,4),(6,0,76,4),(7,0,72,4)]),
 "romantic_nostalgic": dict(tags=["عاشقانه", "نوستالژیک", "پیانو"], bpm=88, bars=24, voice="piano", drums="sorrow",
    chords=[[52,56,59],[45,49,52],[47,51,54],[44,47,52]], arp=[0,1,2,1,0,1,2,1],
    mel=[(0,0,76,2),(0,2,80,2),(1,0,81,3),(1,3,80,1),(2,0,78,2),(2,2,76,2),(3,0,75,4),(4,0,76,2),(4,2,83,2),(5,0,81,4),(6,0,80,2),(6,2,78,2),(7,0,76,4)]),
 # old slow presets stay available for existing catalog rows
 "sad_piano_cello": dict(tags=["غمگین", "احساسی", "پیانو", "آرام"], bpm=68, bars=16, voice="bow", drums=None,
    chords=[[57,60,64],[53,57,60],[48,52,55],[55,59,62]], arp=[0,1,2,3,2,1,2,1],
    mel=[(0,0,76,3),(0,3,72,1),(1,0,69,4),(2,0,72,2),(2,2,71,2),(3,0,67,4),(4,0,76,3),(4,3,79,1),(5,0,77,4),(6,0,76,2),(6,2,72,2),(7,0,71,3),(7,3,69,1)]),
 "sad_piano_slow": dict(tags=["غمگین", "احساسی", "پیانو", "آرام"], bpm=60, bars=16, voice="piano", drums=None,
    chords=[[50,53,57],[46,50,53],[53,57,60],[48,52,55]], arp=[0,2,1,2,0,2,1,2],
    mel=[(0,0,81,2),(0,2,77,2),(1,0,74,3),(1,3,77,1),(2,0,76,2),(2,2,72,2),(3,0,69,4),(4,0,81,2),(4,2,84,2),(5,0,82,3),(5,3,81,1),(6,0,79,2),(6,2,77,2),(7,0,76,4)]),
 "epic_dark": dict(tags=["حماسی", "تاریک", "سینمایی"], bpm=84, bars=16, voice="bow", drums=None,
    chords=[[45,48,52],[41,45,48],[43,47,50],[40,44,47]], arp=[0,0,1,0,2,0,1,0],
    mel=[(0,0,69,4),(1,0,72,4),(2,0,71,2),(2,2,67,2),(3,0,64,4),(4,0,69,2),(4,2,76,2),(5,0,77,4),(6,0,76,2),(6,2,72,2),(7,0,71,4)]),
}
MOOD_TO_PRESET = {"غمگین": ["sorrowful_pulse", "piano_emotional"], "سوزناک": ["sorrowful_pulse"],
                  "احساسی": ["emotional_drive", "piano_emotional"], "حماسی": ["epic_percussive"],
                  "انگیزشی": ["epic_percussive", "piano_hope"], "هیجانی": ["tense_pulse"], "ریتمیک": ["tense_pulse"],
                  "امیدوار": ["piano_hope", "emotional_drive"], "آرام": ["calm_ambient"],
                  "عاشقانه": ["romantic_nostalgic", "piano_hope"], "نوستالژیک": ["romantic_nostalgic", "piano_emotional"]}


def compose(preset, outdir, seed=1):
    """Write <preset>.mp3 (original, copyright-free) into outdir and return its catalog row."""
    p = PRESETS[preset]
    render(preset, p["bpm"], p["chords"], p["arp"], p["mel"], p["bars"], p["voice"], seed, outdir,
           drums=p.get("drums"), arp_step=p.get("arp_step", 0.5))
    mp3 = os.path.join(outdir, preset + ".mp3")
    return dict(id=preset, title=preset, artist="synth (Claude)", file=preset + ".mp3", tags=p["tags"],
                tag_source="synthesized preset", synthesized=True)
