#!/usr/bin/env python3
"""
Generate one audio clip per Vietnamese syllable with VieNeu-TTS.
https://github.com/pnnbao97/VieNeu-TTS

Two ways to use it:

1. From the notebook, in-kernel (the way build_audio.ipynb does it) — load the
   model once and reuse it, so nothing spawns a second copy on the GPU:

       import generate_clips as gc
       tts = gc.load_tts()
       gc.run('south', 'Adam', tts, used_in='data.json', limit=40)   # audition
       gc.run('south', 'Adam', tts, used_in='data.json')             # full run

2. As a script (loads its own model):

       pip install vieneu librosa soundfile      # ffmpeg must be on PATH
       python generate_clips.py --list-voices
       python generate_clips.py --region south --voice "Adam" --used-in data.json

How a clip is made: the model says the bare syllable on its own; the output is
trimmed to the syllable, RMS-normalised to a steady loudness, padded with silence,
and slowed (hỏi and ngã a little more, since their contour carries the tone). If
the model rambles — it sometimes invents an extra word on such short input — the
clip comes out too long and is regenerated.
"""
import csv, os, subprocess, sys, time
import numpy as np
import librosa
import soundfile as sf
from parse import parse

SR = 24000


def load_tts():
    """Load VieNeu once. Reuse the returned object for every clip."""
    from vieneu import Vieneu
    return Vieneu()


def list_voices(tts):
    """[(description, name), ...] for the preset voices."""
    return tts.list_preset_voices()


def speed_for(syllable, speed=0.9, speed_dip=0.8):
    """hỏi and ngã ride on their contour, so slow them a little more."""
    p = parse(syllable)
    return speed_dip if (p and p['tone'] in ('hoi', 'nga')) else speed


def _trimmed(y):
    """Drop the silence either side, keeping the whole syllable."""
    iv = librosa.effects.split(y, top_db=30)
    return y[iv[0][0]:iv[-1][1]] if len(iv) else y


def clean_syllable(tts, syllable, voice, max_len=0.9, retries=5):
    """One bare syllable, regenerated if the model pads it with an extra word."""
    best = None
    for _ in range(max(1, retries)):
        tts.save(tts.infer(syllable, voice=voice), '_one.wav')
        y = _trimmed(librosa.load('_one.wav', sr=SR)[0])
        dur = len(y) / SR
        if best is None or dur < best[0]:
            best = (dur, y)
        if dur <= max_len:
            break
    return best[1]


def encode(y, syllable, out_path, speed=0.9, speed_dip=0.8,
           pad=0.5, target_rms=0.10, fmt='mp3'):
    """Normalise loudness, pad with silence, slow to the tone's speed, encode."""
    rms = float(np.sqrt(np.mean(y ** 2))) + 1e-9
    y = y * (target_rms / rms)
    peak = float(np.max(np.abs(y))) + 1e-9
    if peak > 0.97:
        y = y * (0.97 / peak)
    s = speed_for(syllable, speed, speed_dip)
    # pad *s so the silence is still `pad` seconds after atempo stretches it
    silence = np.zeros(int(pad * s * SR), dtype=y.dtype)
    y = np.concatenate([silence, y, silence])
    sf.write('_seg.wav', y, SR)
    codec = {'mp3': ['-c:a', 'libmp3lame', '-b:a', '64k'],
             'opus': ['-c:a', 'libopus', '-b:a', '32k'],
             'wav': ['-c:a', 'pcm_s16le']}[fmt]
    filt = f'atempo={s}' if s != 1.0 else 'anull'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', '_seg.wav',
                    '-af', filt, '-ar', str(SR), '-ac', '1'] + codec + [out_path],
                   check=True)


def _rows(manifest, used_in, limit):
    rows = list(csv.DictReader(open(manifest, encoding='utf-8-sig')))
    rows.sort(key=lambda r: int(r['freq_rank']) if r['freq_rank'] else 10 ** 9)
    if used_in:
        import json
        used = set(json.load(open(used_in, encoding='utf-8'))['clips'])
        rows = [r for r in rows if r['clip_id'] in used]
    if limit:
        rows = rows[:limit]
    return rows


def run(region=None, voice=None, tts=None, *, outdir=None,
        manifest='vietnamese_clip_manifest.csv', used_in=None, limit=None,
        speed=0.9, speed_dip=0.8, pad=0.5, target_rms=0.10,
        max_len=0.9, retries=5, fmt='mp3', progress_every=25):
    """Generate every missing clip for one accent.

    Pass a `tts` from load_tts() to reuse a loaded model (do this in the
    notebook). It skips clips that already exist, so it is safe to re-run.
    Returns the number of clips made this call.
    """
    if tts is None:
        tts = load_tts()
    if not voice:
        raise ValueError('voice is required')
    if outdir is None:
        outdir = f'audio/{region}' if region else 'audio'
    os.makedirs(outdir, exist_ok=True)

    rows = _rows(manifest, used_in, limit)
    todo = [r for r in rows
            if not os.path.exists(os.path.join(outdir, f"{r['clip_id']}.{fmt}"))]
    label = region or outdir
    print(f'{label}: {len(rows)} clips, {len(todo)} still to make', flush=True)

    start, done = time.time(), 0
    for r in todo:
        out = os.path.join(outdir, f"{r['clip_id']}.{fmt}")
        try:
            y = clean_syllable(tts, r['syllable'], voice, max_len, retries)
            encode(y, r['syllable'], out, speed, speed_dip, pad, target_rms, fmt)
            done += 1
        except Exception as e:
            print(f"  FAILED {r['clip_id']} {r['syllable']}: {e}", file=sys.stderr, flush=True)
        if progress_every and done and done % progress_every == 0:
            rate = done / (time.time() - start)
            left = (len(todo) - done) / rate if rate else 0
            print(f'  {done}/{len(todo)}  {rate:.1f}/s  ~{left / 60:.0f} min left', flush=True)

    for tmp in ('_one.wav', '_seg.wav'):
        if os.path.exists(tmp):
            os.remove(tmp)
    print(f'{label}: done ({done} made)', flush=True)
    return done


def _cli():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', default='vietnamese_clip_manifest.csv')
    ap.add_argument('--region', choices=['south', 'north'])
    ap.add_argument('--outdir', default=None)
    ap.add_argument('--used-in', default=None)
    ap.add_argument('--voice', default=None)
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--format', default='mp3', choices=['mp3', 'opus', 'wav'])
    ap.add_argument('--list-voices', action='store_true')
    ap.add_argument('--speed', type=float, default=0.9)
    ap.add_argument('--speed-dip', type=float, default=0.8)
    ap.add_argument('--pad', type=float, default=0.5)
    ap.add_argument('--target-rms', type=float, default=0.10)
    ap.add_argument('--max-len', type=float, default=0.9)
    ap.add_argument('--retries', type=int, default=5)
    a = ap.parse_args()
    tts = load_tts()
    if a.list_voices:
        for desc, name in list_voices(tts):
            print(f'{name}\t{desc}')
        return
    if not a.voice:
        sys.exit('pick a voice first: --list-voices')
    run(a.region, a.voice, tts, outdir=a.outdir, manifest=a.manifest,
        used_in=a.used_in, limit=a.limit, speed=a.speed, speed_dip=a.speed_dip,
        pad=a.pad, target_rms=a.target_rms, max_len=a.max_len,
        retries=a.retries, fmt=a.format)


if __name__ == '__main__':
    _cli()
