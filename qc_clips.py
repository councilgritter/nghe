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
ap.add_argument('--manifest', default='data/vietnamese_clip_manifest.csv')
ap.add_argument('--outdir', default='docs/audio')
ap.add_argument('--format', default='mp3')
ap.add_argument('--model', default='vinai/PhoWhisper-small')
ap.add_argument('--batch', type=int, default=16)
args = ap.parse_args()

import librosa  # noqa: E402
from transformers import pipeline  # noqa: E402

asr = pipeline('automatic-speech-recognition', model=args.model, chunk_length_s=10)

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

out = []
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

with open('qc_report.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)

from collections import Counter  # noqa: E402
print(Counter(r['status'] for r in out))
print('wrote qc_report.csv')
