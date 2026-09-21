#!/usr/bin/env python3
"""
Quality-control the generated clips: transcribe each one back with PhoWhisper
and flag any that don't come back as the syllable they were supposed to be.

This is the step that stops a mispronounced clip from teaching you a wrong tone.

    pip install transformers torch librosa
    python qc_clips.py --outdir audio

Writes qc_report.csv with a 'status' column: ok | mismatch | tone_mismatch.
Review the mismatches by ear — some will be ASR error rather than TTS error,
especially on low-frequency syllables.
"""
import argparse, csv, os, unicodedata

ap = argparse.ArgumentParser()
ap.add_argument('--manifest', default='vietnamese_clip_manifest.csv')
ap.add_argument('--region', choices=['south', 'north'],
                help='check audio/<region>/ and write qc_report_<region>.csv')
ap.add_argument('--outdir', default=None)
ap.add_argument('--report', default=None)
ap.add_argument('--format', default='mp3')
ap.add_argument('--model', default='vinai/PhoWhisper-small')
ap.add_argument('--batch', type=int, default=16)
ap.add_argument('--fresh', action='store_true',
                help='ignore an existing qc_report.csv instead of resuming from it')
args = ap.parse_args()
if not args.outdir:
    args.outdir = f'audio/{args.region}' if args.region else 'audio'
if not args.report:
    args.report = f'qc_report_{args.region}.csv' if args.region else 'qc_report.csv'

import librosa  # noqa: E402
import torch  # noqa: E402
from transformers import pipeline  # noqa: E402

device = 0 if torch.cuda.is_available() else -1
print('device:', torch.cuda.get_device_name(0) if device == 0
      else 'CPU - no GPU found, this will be very slow', flush=True)
asr = pipeline('automatic-speech-recognition', model=args.model,
               chunk_length_s=10, device=device)

TONE_MARKS = set('\u0300\u0301\u0309\u0303\u0323')


def strip_tone(s):
    return unicodedata.normalize(
        'NFC', ''.join(c for c in unicodedata.normalize('NFD', s)
                       if c not in TONE_MARKS))


def clean(s):
    s = s.strip().lower()
    return ''.join(c for c in s if c.isalpha() or c in 'ăâđêôơư' or
                   unicodedata.combining(c))


rows = list(csv.DictReader(open(args.manifest, encoding='utf-8-sig')))
rows = [r for r in rows
        if os.path.exists(os.path.join(args.outdir, f"{r['clip_id']}.{args.format}"))]
print(f'{len(rows)} clips to check')

REPORT = args.report
out = []
if os.path.exists(REPORT) and not args.fresh:
    out = list(csv.DictReader(open(REPORT, encoding='utf-8-sig')))
    done = {r['clip_id'] for r in out}
    rows = [r for r in rows if r['clip_id'] not in done]
    print(f'resuming: {len(done)} already checked, {len(rows)} to go')


def save():
    if not out:
        return
    with open(REPORT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)


for i in range(0, len(rows), args.batch):
    chunk = rows[i:i + args.batch]
    paths = [os.path.join(args.outdir, f"{r['clip_id']}.{args.format}") for r in chunk]
    audios = [librosa.load(p, sr=16000)[0] for p in paths]
    results = asr(audios, batch_size=len(audios))
    for r, res in zip(chunk, results):
        heard = clean(res['text'])
        want = clean(r['syllable'])
        if heard == want:
            status = 'ok'
        elif strip_tone(heard) == strip_tone(want):
            status = 'tone_mismatch'
        else:
            status = 'mismatch'
        out.append({**r, 'heard': heard, 'status': status})
    print(f'{min(i+args.batch, len(rows))}/{len(rows)}', flush=True)
    if (i // args.batch) % 25 == 24:
        save()

save()

from collections import Counter  # noqa: E402
print(Counter(r['status'] for r in out))
print('wrote', REPORT)
