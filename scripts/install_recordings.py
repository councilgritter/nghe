#!/usr/bin/env python3
"""
Install approved human recordings over the AI clips.

Run by .github/workflows/install-recordings.yml, but works locally too.
It talks to the collector (apps_script/collector.gs) over HTTP — no Google Drive
mount needed — so it runs anywhere with ffmpeg and internet.

Two modes:
    python scripts/install_recordings.py          # fetch approved, install, list rows
    python scripts/install_recordings.py --mark    # tell the collector they're installed

Env:
    COLLECTOR_URL   the Apps Script /exec URL
    COLLECTOR_KEY   optional shared key (matches KEY in collector.gs)

Each approved recording is trimmed, loudness-matched and padded to look like the
generated clips, then written to audio/<region>/<clip>.mp3 by clip_id + region —
so an approved Southern take only ever replaces the Southern clip.
"""
import base64, json, os, subprocess, sys, tempfile, urllib.parse, urllib.request

URL = os.environ.get('COLLECTOR_URL', '').rstrip('/')
KEY = os.environ.get('COLLECTOR_KEY', '')
ROWS_FILE = 'installed_rows.json'

# trim silence, match loudness to the AI clips, pad 0.5s each side, encode like them
FILTER = ('silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.05,'
          'areverse,'
          'silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.05,'
          'areverse,'
          'loudnorm=I=-16:TP=-1.5:LRA=7,'
          'adelay=500,apad=pad_dur=0.5')


def get(params):
    q = urllib.parse.urlencode({**params, **({'key': KEY} if KEY else {})})
    with urllib.request.urlopen(f'{URL}?{q}', timeout=60) as r:
        return json.load(r)


def post(payload):
    body = json.dumps({**payload, **({'key': KEY} if KEY else {})}).encode('utf-8')
    req = urllib.request.Request(URL, data=body,
                                 headers={'Content-Type': 'text/plain;charset=utf-8'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def encode(src, out):
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-af', FILTER,
                    '-ac', '1', '-ar', '24000', '-c:a', 'libmp3lame', '-b:a', '64k', out],
                   check=True)


def install():
    if not URL:
        sys.exit('COLLECTOR_URL is not set')
    queue = get({'approved': '1'})
    print(f'{len(queue)} approved recording(s) to install', flush=True)
    done = []
    for r in queue:
        try:
            rec = get({'rec': r['row']})
            raw = base64.b64decode(rec['b64'])
            ext = 'm4a' if 'mp4' in (rec.get('mime') or '') else 'webm'
            with tempfile.NamedTemporaryFile(suffix='.' + ext, delete=False) as tf:
                tf.write(raw); src = tf.name
            outdir = os.path.join('audio', r['region'])
            os.makedirs(outdir, exist_ok=True)
            out = os.path.join(outdir, f"{r['clip']}.mp3")
            encode(src, out)
            os.remove(src)
            done.append(r['row'])
            print(f"  installed {r['syllable']} -> {out}", flush=True)
        except Exception as e:
            print(f"  FAILED row {r.get('row')} {r.get('clip')}: {e}", file=sys.stderr, flush=True)
    json.dump(done, open(ROWS_FILE, 'w'))
    print(f'{len(done)} installed; rows saved to {ROWS_FILE}', flush=True)


def mark():
    if not os.path.exists(ROWS_FILE):
        print('no rows to mark'); return
    rows = json.load(open(ROWS_FILE))
    if not rows:
        print('no rows to mark'); return
    post({'type': 'installed', 'rows': rows})
    print(f'marked {len(rows)} row(s) installed')


if __name__ == '__main__':
    mark() if '--mark' in sys.argv else install()
