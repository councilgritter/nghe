#!/usr/bin/env python3
"""
Generate one audio clip per Vietnamese syllable with VieNeu-TTS.
https://github.com/pnnbao97/VieNeu-TTS

You do not normally run this by hand — build_audio.ipynb calls it.
To run it yourself:

    pip install vieneu          # ffmpeg must also be on PATH

First run this to see the voices and pick one per accent:
    python generate_clips.py --list-voices

Clips go in audio/<region>/ where region is south, north or central.
Spot-check 40 clips BEFORE committing to the full run:
    python generate_clips.py --region north --voice "<name>" --limit 40

Then the full run (resumable — safe to Ctrl-C and restart). --used-in makes
only the clips the app actually plays, which skips the unused ~15%:
    python generate_clips.py --region north --voice "<name>" --used-in data.json
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
ap.add_argument('--batch', type=int, default=16, help='0 disables infer_batch')
ap.add_argument('--format', default='mp3', choices=['mp3', 'opus', 'wav'])
ap.add_argument('--list-voices', action='store_true')
ap.add_argument('--carrier', default=None,
                help="optional carrier, e.g. 'Từ {} .' — improves prosody on bare syllables")
ap.add_argument('--speed', type=float, default=1.0,
                help='tempo multiplier applied at encode: 0.9 = a touch slower, 1.1 = faster')
args = ap.parse_args()
if not args.outdir:
    args.outdir = f'audio/{args.region}' if args.region else 'audio'

from vieneu import Vieneu  # noqa: E402

tts = Vieneu()

if args.list_voices:
    for desc, name in tts.list_preset_voices():
        print(f'{name}\t{desc}')
    sys.exit(0)

if not args.voice:
    sys.exit('pick a voice first: --list-voices')

os.makedirs(args.outdir, exist_ok=True)
os.makedirs('_wav', exist_ok=True)

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
print(f'{len(rows)} clips requested, {len(todo)} still to make')


def encode(wav_path, out_path):
    """Trim leading/trailing silence, normalise loudness, encode."""
    filt = ('silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02,'
            'areverse,'
            'silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02,'
            'areverse,'
            'loudnorm=I=-18:TP=-2:LRA=7')
    if args.speed != 1.0:
        filt += f',atempo={args.speed}'
    codec = {'mp3': ['-c:a', 'libmp3lame', '-b:a', '64k'],
             'opus': ['-c:a', 'libopus', '-b:a', '32k'],
             'wav': ['-c:a', 'pcm_s16le']}[args.format]
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wav_path,
                    '-af', filt, '-ac', '1', '-ar', '24000'] + codec + [out_path],
                   check=True)


def text_for(syllable):
    return args.carrier.format(syllable) if args.carrier else syllable


start = time.time()
done = 0
step = max(1, args.batch)

for i in range(0, len(todo), step):
    chunk = todo[i:i + step]
    texts = [text_for(r['syllable']) for r in chunk]
    try:
        if args.batch and hasattr(tts, 'infer_batch') and len(chunk) > 1:
            audios = tts.infer_batch(texts, voice=args.voice)
        else:
            audios = [tts.infer(t, voice=args.voice) for t in texts]
    except Exception as e:
        print(f'  batch failed ({e}) — falling back to one at a time', file=sys.stderr)
        audios = []
        for t in texts:
            try:
                audios.append(tts.infer(t, voice=args.voice))
            except Exception as e2:
                print(f'  FAILED {t}: {e2}', file=sys.stderr)
                audios.append(None)

    for r, audio in zip(chunk, audios):
        if audio is None:
            continue
        wav = os.path.join('_wav', f"{r['clip_id']}.wav")
        tts.save(audio, wav)
        encode(wav, os.path.join(args.outdir, f"{r['clip_id']}.{args.format}"))
        os.remove(wav)
        done += 1

    if done:
        rate = done / (time.time() - start)
        left = (len(todo) - done) / rate if rate else 0
        print(f'{done}/{len(todo)}  {rate:.1f}/s  ~{left/60:.0f} min left', flush=True)

print('done')
