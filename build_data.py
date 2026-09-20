#!/usr/bin/env python3
"""
Turn the two CSVs into the compact data.json the app loads.

    python build_data.py --items vietnamese_drill_items.csv \
                         --clips vietnamese_clip_manifest.csv \
                         --out site/data.json

Re-run this whenever you regenerate the CSVs. It does not need the audio to
exist — the app falls back to browser speech for any clip that is missing.
"""
import argparse, csv, json, os, unicodedata

ap = argparse.ArgumentParser()
ap.add_argument('--items', default='data/vietnamese_drill_items.csv')
ap.add_argument('--clips', default='data/vietnamese_clip_manifest.csv')
ap.add_argument('--out', default='docs/data.json')
ap.add_argument('--max-rank', type=int, default=3000,
                help='cap TARGET frequency rank; the corpus tail is noisy')
ap.add_argument('--drop-merged', action='store_true',
                help='drop hoi/nga items that a Southern voice will not distinguish')
args = ap.parse_args()

AXES = ['tone', 'vowel', 'onset', 'final']
DIFF = ['easy', 'medium', 'hard']

TONE_LABEL = {'ngang': 'ngang (level)', 'huyen': 'huyền (falling)',
              'sac': 'sắc (rising)', 'hoi': 'hỏi (dipping)',
              'nga': 'ngã (broken)', 'nang': 'nặng (heavy)'}

clips = {}
for r in csv.DictReader(open(args.clips, encoding='utf-8-sig')):
    clips[r['syllable']] = r['clip_id']

syllables, syl_index = [], {}


def sid(s):
    if s not in syl_index:
        syl_index[s] = len(syllables)
        syllables.append(s)
    return syl_index[s]


contrasts, con_index = [], {}


def cid(axis, a, b):
    def label(x):
        if axis == 'tone':
            return TONE_LABEL.get(x, x)
        return x if x else '–'
    key = (axis, *sorted([a, b]))
    if key not in con_index:
        con_index[key] = len(contrasts)
        contrasts.append({'axis': axis,
                          'label': f'{label(key[1])} / {label(key[2])}'})
    return con_index[key]


items, skipped = [], 0
for r in csv.DictReader(open(args.items, encoding='utf-8-sig')):
    rank = int(r['freq_rank'])
    merged = r['southern_merged'] == '1'
    if rank > args.max_rank or (args.drop_merged and merged):
        skipped += 1
        continue
    opts = [r['option_1'], r['option_2'], r['option_3'], r['option_4']]
    if any(o not in clips for o in opts):
        skipped += 1
        continue
    # the contrast between the target and its nearest distractor labels the item
    items.append([
        sid(opts[0]), sid(opts[1]), sid(opts[2]), sid(opts[3]),
        AXES.index(r['axis']),
        DIFF.index(r['difficulty']),
        0,  # contrast id, filled in by the second pass below
        rank,
        1 if merged else 0,
    ])

# second pass: label each item by the real phonological contrast between the
# target and its nearest distractor. Character diffing is not good enough here:
# "an" vs "ang" differ in coda n/ng, but a naive diff reports "nothing / g".
from parse import parse  # noqa: E402

FIELD = {'tone': 'tone', 'vowel': 'nucleus', 'onset': 'onset', 'final': 'coda'}

unlabelled = 0
for it in items:
    axis = AXES[it[4]]
    pt, pd = parse(syllables[it[0]]), parse(syllables[it[1]])
    if pt is None or pd is None:
        unlabelled += 1
        continue
    f = FIELD[axis]
    it[6] = cid(axis, pt[f], pd[f])
if unlabelled:
    print(f'note: {unlabelled} items could not be phonologically labelled')

os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
json.dump({
    'syllables': syllables,
    'clips': [clips[s] for s in syllables],
    'axes': AXES,
    'difficulties': DIFF,
    'contrasts': contrasts,
    'items': items,
}, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

size = os.path.getsize(args.out)
print(f'{len(items)} items, {len(syllables)} syllables, {len(contrasts)} contrasts')
print(f'skipped {skipped} (rank > {args.max_rank}' +
      (', merged' if args.drop_merged else '') + ')')
print(f'wrote {args.out}  ({size/1024:.0f} KB)')
