# Human recordings — planned, not built yet

A way for users to record the **correct** pronunciation of a syllable, have it
reviewed, and install the approved ones over the AI clips. Additive: it layers on
top of the generated audio and doesn't touch the generation pipeline.

## Status

- **Not in the app.** The current `index.html` has no flag or record UI. An older
  version did — see git history (the 32 KB `Index.html`, e.g. commit `2f4a906`),
  which had a flag button, a recorder, and a "reasons" panel.
- **Installer exists but is orphaned:** `install_approved.py` (a Colab cell). It
  pulls approved recordings, trims/normalises them with ffmpeg, and writes them
  over the AI clip. It already handles per-accent folders via a `region` field.
- **Collector never built.** The middle piece — an endpoint the app posts to, and
  the sheet a reviewer approves in — was never in the repo.

## The chain

```
app: record correct pronunciation      →  collector (Google Apps Script)
  (tagged clip_id + region)                 writes a row to a Google Sheet
                                             + saves the audio to Drive
                                                   │
reviewer marks approve / reject in the Sheet  ────┘
                                                   │
install_approved.py (Colab): pulls approved rows, processes the audio,
  installs over audio/<region>/<clip_id>.mp3, commits and pushes
```

## Key design constraint (the important one)

**Every recording is tagged with its accent.** A recording carries both:

- `clip_id` — which syllable it corrects
- `region` — `south` or `north`

so an approved **Southern** recording replaces `audio/south/<clip_id>.mp3` and
**not** the Northern clip. `install_approved.py` already reads a `region` field and
writes to `audio/<region>/`, so the installer side is ready; the record UI must
capture the accent that was active when the user recorded (the app already knows it
as `S.cfg.region`).

## To build later — three pieces

1. **Record + flag UI in `index.html`** — a flag button on a clip, a recorder, and
   a send action. Post `clip_id`, `region`, `syllable`, and the audio to the collector.
   (Reference the old `Index.html` in git history for the interaction, but rebuild it
   against the current single-file app and the south/north accent model.)
2. **Collector** — a Google Apps Script web app that appends a row to a Google Sheet
   (with an `approved` column) and stores the audio file in a Drive folder. Optional
   shared `KEY` to stop random posts.
3. **Wire `install_approved.py`** — set its `COLLECTOR` URL, run it in Colab; it
   installs every approved recording over the matching AI clip, per accent, and pushes.

Nothing here blocks shipping the AI voices — human recordings replace individual
clips by `clip_id` + `region` whenever they're approved.
