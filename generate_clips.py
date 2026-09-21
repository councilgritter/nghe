#!/usr/bin/env python3
"""
Generate one audio clip per Vietnamese syllable with VieNeu-TTS.
https://github.com/pnnbao97/VieNeu-TTS

You do not normally run this by hand — build_audio.ipynb calls it.
To run it yourself:

    pip install vieneu librosa soundfile   # ffmpeg must also be on PATH

First run this to see the voices and pick one per accent:
    python generate_clips.py --list-voices

Clips go in audio/<region>/ where region is south or north.
Spot-check 40 clips BEFORE committing to the full run:
    python generate_clips.py --region north --voice "<name>" --limit 40

Then the full run (resumable — safe to Ctrl-C and restart). --used-in makes
only the clips the app actually plays, which skips the unused ~15%:
    python generate_clips.py --region north --voice "<name>" --used-in data.json

How a clip is made: the model says the bare syllable on its own; the output is
trimmed to the syllable, RMS-normalised to a steady loudness, padded with
silence, and slowed (hỏi and ngã get slowed a little more, since their contour
carries the tone). If the model rambles — it sometimes invents an extra word on
such short input — the clip comes out too long and is regenerated.
"""
import argparse, csv, os, subprocess, sys, time

ap = argparse.ArgumentParser()
ap.add_argument('--manifest', default='vietnamese_clip_manifest.csv')
ap.add_argument('--region', choices=['south', 'north'],
                help='accent; clips are written to audio/<region>/')
ap.add_argument('--outdir', default=None, help='overrides the folder chosen by --region')
ap.add_argument('--used-in', default=None, metavar='DATA_JSON',
                help='only make clips that this data.json references')
ap.add_argument('--voice', default=None)
ap.add_argument('--limit', type=int, default=None, help='only the N most frequent syllables')
ap.add_argument('--format', default='mp3', choices=['mp3', 'opus', 'wav'])
ap.add_argument('--list-voices', action='store_true')
ap.add_argument('--speed', type=float, default=0.9,
                help='tempo for the level tones (ngang, huyền, sắc, nặng)')
ap.add_argument('--speed-dip', type=float, default=0.8,
                help='tempo for the contour tones hỏi and ngã, usually a touch slower')
ap.add_argument('--pad', type=float, default=0.5, help='seconds of silence on each side')
ap.add_argument('--target-rms', type=float, default=0.10, help='loudness each clip is scaled to')
ap.add_argument('--max-len', type=float, default=0.9,
                help='a trimmed syllable longer than this is treated as a hallucination and remade')
ap.add_argument('--retries', type=int, default=5, help='regeneration attempts when a clip is too long')
args = ap.parse_args()
if not args.outdir:
    args.outdir = f'audio/{args.region}' if args.region else 'audio'

import numpy as np  # noqa: E402
import librosa  # noqa: E402
import soundfile as sf  # noqa: E402
from vieneu import Vieneu  # noqa: E402
from parse import parse  # noqa: E402

SR = 24000
tts = Vieneu()

if args.list_voices:
    for desc, name in tts.list_preset_voices():
        print(f'{name}\t{desc}')
    sys.exit(0)

if not args.voice:
    sys.exit('pick a voice first: --list-voices')

os.makedirs(args.outdir, exist_ok=True)


def speed_for(syllable):
    """hỏi and ngã ride on their contour, so slow them a little more."""
    p = parse(syllable)
    return args.speed_dip if (p and p['tone'] in ('hoi', 'nga')) else args.speed


def trimmed(y):
    """Drop the silence either side, keeping the whole syllable."""
    iv = librosa.effects.split(y, top_db=30)
    return y[iv[0][0]:iv[-1][1]] if len(iv) else y


def clean_syllable(syllable):
    """One bare syllable, regenerated if the model pads it with an extra word."""
    best = None
    for _ in range(max(1, args.retries)):
        tts.save(tts.infer(syllable, voice=args.voice), '_one.wav')
        y = trimmed(librosa.load('_one.wav', sr=SR)[0])
        dur = len(y) / SR
        if best is None or dur < best[0]:
            best = (dur, y)
        if dur <= args.max_len:
            break
    return best[1]


def encode(y, syllable, out_path):
    """Normalise loudness, pad with silence, slow to the tone's speed, encode."""
    rms = float(np.sqrt(np.mean(y ** 2))) + 1e-9
    y = y * (args.target_rms / rms)
    peak = float(np.max(np.abs(y))) + 1e-9
    if peak > 0.97:
        y = y * (0.97 / peak)
    speed = speed_for(syllable)
    # pad *speed so the silence is still `--pad` seconds after atempo stretches it
    pad = np.zeros(int(args.pad * speed * SR), dtype=y.dtype)
    y = np.concatenate([pad, y, pad])
    sf.write('_seg.wav', y, SR)
    codec = {'mp3': ['-c:a', 'libmp3lame', '-b:a', '64k'],
             'opus': ['-c:a', 'libopus', '-b:a', '32k'],
             'wav': ['-c:a', 'pcm_s16le']}[args.format]
    filt = f'atempo={speed}' if speed != 1.0 else 'anull'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', '_seg.wav',
                    '-af', filt, '-ar', str(SR), '-ac', '1'] + codec + [out_path],
                   check=True)


rows = list(csv.DictReader(open(args.manifest, encoding='utf-8-sig')))
rows.sort(key=lambda r: int(r['freq_rank']) if r['freq_rank'] else 10**9)
if args.used_in:
    import json
    used = set(json.load(open(args.used_in, encoding='utf-8'))['clips'])
    rows = [r for r in rows if r['clip_id'] in used]
if args.limit:
    rows = rows[:args.limit]

todo = [r for r in rows
        if not os.path.exists(os.path.join(args.outdir, f"{r['clip_id']}.{args.format}"))]
print(f'{len(rows)} clips requested, {len(todo)} still to make', flush=True)

start = time.time()
done = 0
for r in todo:
    out = os.path.join(args.outdir, f"{r['clip_id']}.{args.format}")
    try:
        encode(clean_syllable(r['syllable']), r['syllable'], out)
        done += 1
    except Exception as e:
        print(f"  FAILED {r['clip_id']} {r['syllable']}: {e}", file=sys.stderr)
    if done and done % 25 == 0:
        rate = done / (time.time() - start)
        left = (len(todo) - done) / rate if rate else 0
        print(f'{done}/{len(todo)}  {rate:.1f}/s  ~{left/60:.0f} min left', flush=True)

for tmp in ('_one.wav', '_seg.wav'):
    if os.path.exists(tmp):
        os.remove(tmp)
print('done', flush=True)
