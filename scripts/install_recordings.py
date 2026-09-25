#!/usr/bin/env python3
"""
Install approved human recordings over the AI clips — straight into Cloudflare R2.

Run by .github/workflows/install-recordings.yml. It talks to the collector
(apps_script/collector.gs) over HTTP for the approved queue and the audio, and
uploads each processed clip to the R2 bucket, overwriting the AI object at
<region>/<clip>.mp3. No git, no commit — the app serves from R2.

Env:
    COLLECTOR_URL          the Apps Script /exec URL
    COLLECTOR_KEY          optional shared key (matches KEY in collector.gs)
    R2_ENDPOINT            https://<accountid>.r2.cloudflarestorage.com  (S3 endpoint, not r2.dev)
    R2_BUCKET              e.g. nghe-audio
    R2_ACCESS_KEY_ID       an R2 API token with Object Read & Write on the bucket
    R2_SECRET_ACCESS_KEY   its secret

Each recording is trimmed, loudness-matched and padded to look like the generated
clips, then uploaded to <region>/<clip>.mp3 — so an approved Southern take only
ever replaces the Southern clip.
"""
import base64, json, os, re, subprocess, sys, tempfile, time, urllib.parse, urllib.request

import boto3  # noqa: E402

URL = os.environ.get('COLLECTOR_URL', '').rstrip('/')
KEY = os.environ.get('COLLECTOR_KEY', '')
BUCKET = os.environ['R2_BUCKET']

# match loudness first (so quiet takes get boosted), THEN trim silence at a gentle
# threshold (so quiet speech survives), then pad 0.5s each side.
FILTER = ('loudnorm=I=-16:TP=-1.5:LRA=7,'
          'silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.05,'
          'areverse,'
          'silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.05,'
          'areverse,'
          'adelay=500,apad=pad_dur=0.5')

# a finished clip should peak near 0 dB; anything this quiet is effectively silence
MIN_PEAK_DB = -15.0


def peak_db(path):
    """Loudest sample in dBFS, or None if it couldn't be measured."""
    out = subprocess.run(['ffmpeg', '-i', path, '-af', 'volumedetect', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    m = re.search(r'max_volume:\s*(-?\d+(?:\.\d+)?) dB', out)
    return float(m.group(1)) if m else None


def r2():
    return boto3.client('s3', endpoint_url=os.environ['R2_ENDPOINT'],
                        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
                        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
                        region_name='auto')


def get(params, tries=4):
    # Apps Script occasionally answers a GET with a redirect/HTML interstitial
    # instead of JSON; retry a few times and surface the body if it never parses.
    q = urllib.parse.urlencode({**params, **({'key': KEY} if KEY else {})})
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(f'{URL}?{q}', timeout=90) as r:
                body = r.read().decode('utf-8', 'replace')
            return json.loads(body)
        except Exception as e:
            last = e
            head = (body[:200] if 'body' in dir() and body else '')
            print(f'  collector GET {params} attempt {i + 1}/{tries} failed: {e}'
                  + (f' | response head: {head!r}' if head else ''), file=sys.stderr, flush=True)
            body = ''
            time.sleep(4)
    raise last


def post(payload):
    body = json.dumps({**payload, **({'key': KEY} if KEY else {})}).encode('utf-8')
    req = urllib.request.Request(URL, data=body,
                                 headers={'Content-Type': 'text/plain;charset=utf-8'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def encode(src, out, crop_start=None, crop_end=None):
    filt = FILTER
    if crop_start is not None and crop_end is not None and crop_end > crop_start:
        # crop to the reviewer's selection first, then trim/normalise/pad as usual
        filt = f'atrim=start={crop_start}:end={crop_end},asetpts=PTS-STARTPTS,' + FILTER
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-af', filt,
                    '-ac', '1', '-ar', '24000', '-c:a', 'libmp3lame', '-b:a', '64k', out],
                   check=True)


def main():
    if not URL:
        sys.exit('COLLECTOR_URL is not set')
    s3 = r2()
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
            out = src + '.mp3'
            encode(src, out, r.get('cropStart'), r.get('cropEnd'))
            key = f"{r['region']}/{r['clip']}.mp3"
            pk = peak_db(out)
            if pk is None or pk < MIN_PEAK_DB:
                # too quiet after processing — don't overwrite the AI clip with silence.
                # Left un-marked so it stays pending; re-record it louder.
                print(f"  SKIPPED (near-silent, peak {pk} dB): {r['syllable']} {key} — AI clip kept",
                      file=sys.stderr, flush=True)
                os.remove(src); os.remove(out)
                continue
            s3.upload_file(out, BUCKET, key, ExtraArgs={'ContentType': 'audio/mpeg'})
            os.remove(src); os.remove(out)
            done.append(r['row'])
            print(f"  installed {r['syllable']} -> {key}  (peak {pk} dB)", flush=True)
        except Exception as e:
            print(f"  FAILED row {r.get('row')} {r.get('clip')}: {e}", file=sys.stderr, flush=True)
    if done:
        try:
            post({'type': 'installed', 'rows': done})
        except Exception as e:
            print(f'  uploaded but could not mark installed: {e}', file=sys.stderr, flush=True)
    print(f'{len(done)} installed', flush=True)


if __name__ == '__main__':
    main()
