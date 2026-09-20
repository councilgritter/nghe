"""Decompose attested Vietnamese syllables into onset / glide / nucleus / coda / tone."""
import unicodedata, json, collections

TONE_MARKS = {'\u0300': 'huyen', '\u0301': 'sac', '\u0309': 'hoi',
              '\u0303': 'nga', '\u0323': 'nang'}

ONSETS = ['ngh', 'ng', 'nh', 'ch', 'gh', 'gi', 'kh', 'ph', 'th', 'tr', 'qu',
          'b', 'c', 'd', 'đ', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's',
          't', 'v', 'x']

CODAS = ['ng', 'nh', 'ch', 'c', 'm', 'n', 'p', 't', 'i', 'y', 'o', 'u']

NUCLEI = ['iê', 'yê', 'uô', 'ươ', 'ia', 'ya', 'ua', 'ưa', 'uơ',
          'a', 'ă', 'â', 'e', 'ê', 'i', 'o', 'ô', 'ơ', 'u', 'ư', 'y']

VOWEL_CHARS = set('aăâeêioôơuưy')


def strip_tone(s):
    """Return (toneless_syllable, tone_name)."""
    d = unicodedata.normalize('NFD', s)
    tone = 'ngang'
    out = []
    for ch in d:
        if ch in TONE_MARKS:
            tone = TONE_MARKS[ch]
        else:
            out.append(ch)
    return unicodedata.normalize('NFC', ''.join(out)), tone


def split_onset(base):
    for o in ONSETS:
        if base.startswith(o):
            rest = base[len(o):]
            if not rest:
                continue
            # 'gi'/'qu' need a following vowel to count as those onsets
            if o in ('gi', 'qu') and rest[0] not in VOWEL_CHARS:
                continue
            if rest[0] in VOWEL_CHARS:
                return o, rest
    # bare 'gi' (e.g. gì) = onset gi + nucleus i
    if base == 'gi':
        return 'gi', 'i'
    if base and base[0] in VOWEL_CHARS:
        return '', base
    return None, None


def split_rime(rime):
    """rime -> (glide, nucleus, coda) or None."""
    for coda in [''] + CODAS:
        if coda and not rime.endswith(coda):
            continue
        body = rime[:len(rime) - len(coda)] if coda else rime
        if not body:
            continue
        for nuc in NUCLEI:
            if body.endswith(nuc):
                glide = body[:len(body) - len(nuc)]
                if glide in ('', 'o', 'u'):
                    return glide, nuc, coda
    return None


def parse(syllable):
    base, tone = strip_tone(syllable)
    onset, rime = split_onset(base)
    if rime is None:
        return None
    sr = split_rime(rime)
    if sr is None:
        return None
    glide, nucleus, coda = sr
    return {'syllable': syllable, 'base': base, 'onset': onset,
            'glide': glide, 'nucleus': nucleus, 'coda': coda, 'tone': tone}


if __name__ == '__main__':
    lines = [l.strip() for l in open('syllables.txt', encoding='utf-8') if l.strip()]
    parsed, failed = [], []
    for rank, s in enumerate(lines, 1):
        p = parse(s)
        if p is None:
            failed.append(s)
        else:
            p['rank'] = rank
            parsed.append(p)
    print(f'parsed {len(parsed)}  failed {len(failed)}')
    print('failures:', failed[:40])
    json.dump(parsed, open('parsed.json', 'w', encoding='utf-8'), ensure_ascii=False)
    for field in ('onset', 'glide', 'nucleus', 'coda', 'tone'):
        c = collections.Counter(p[field] for p in parsed)
        print(f'{field}: {len(c)} values ->', dict(c.most_common(12)))
