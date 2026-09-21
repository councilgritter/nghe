# ---- Paste into a new Colab cell. Run after cells 1 and 2. ----
# Installs every approved human recording over the generated clip, then pushes.

COLLECTOR = 'PASTE-YOUR-APPS-SCRIPT-EXEC-URL-HERE'
KEY       = ''        # same as KEY in the Apps Script, if you set one
REC_DIR   = '/content/drive/MyDrive/Nghe recordings'
SPEED     = 1.0       # human speech is natural pace; set 0.85 to match the AI clips

import os, json, subprocess, urllib.request, urllib.parse

url = COLLECTOR + '?approved=1' + ('&key=' + urllib.parse.quote(KEY) if KEY else '')
rows = json.load(urllib.request.urlopen(url))
print(len(rows), 'approved recordings')

FILTER = ('silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.02,'
          'areverse,silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.02,'
          'areverse,apad=pad_dur=0.25,loudnorm=I=-18:TP=-2:LRA=7')
if SPEED != 1.0:
    FILTER += f',atempo={SPEED}'

installed, missing = 0, []
for r in rows:
    src = os.path.join(REC_DIR, r['file'])
    if not os.path.exists(src):
        missing.append(r['file']); continue
    region = str(r['region'] or 'flat')
    outdir = 'audio' if region == 'flat' else f'audio/{region}'
    os.makedirs(outdir, exist_ok=True)
    out = f"{outdir}/{r['clip']}.mp3"
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-af', FILTER,
                    '-ac', '1', '-ar', '24000', '-c:a', 'libmp3lame', '-b:a', '64k', out],
                   check=True)
    installed += 1
    print('  installed', r['syllable'], '->', out)

print(f'\n{installed} installed')
if missing:
    print('not found in Drive (sync lag?):', missing)

if installed:
    !git add -A
    !git -c commit.gpgsign=false commit -m "Install approved human recordings"
    !git push origin HEAD:main
