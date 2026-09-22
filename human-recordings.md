# Human recordings — planned, not built yet

A way for users to record the **correct** pronunciation of a syllable, have it
reviewed, and install the approved ones over the AI clips. Additive: it layers on
top of the generated audio and doesn't touch the generation pipeline.

## Status — built

- **App UI (done):** `index.html` has a Flag button + reasons panel + optional
  recorder, tagging each flag/recording with `clip_id` + `region`. Flags stay local
  (CSV export in Settings) until `FLAG_ENDPOINT` is set; recording is offered once it is.
- **Collector + review (done):** `apps_script/collector.gs` + `apps_script/review.html`
  — one bound Google Apps Script that logs flags/recordings to a Sheet (audio to Drive),
  serves a review page (AI original vs. suggestion, Approve/Reject), and exposes the
  approved queue. Deploy per `apps_script/README.md`, then put its `/exec` URL in
  `FLAG_ENDPOINT`.
- **Install Action (done):** `.github/workflows/install-recordings.yml` +
  `scripts/install_recordings.py` — fetches approved recordings from the collector,
  ffmpeg-processes them to match the AI clips, installs over `audio/<region>/<clip>.mp3`,
  pushes with the built-in token, and marks rows installed. Run it from the Actions tab.
- **Legacy:** `install_approved.py` (the old Colab installer) is superseded by the Action.

**To switch it all on:** deploy the Apps Script, paste its `/exec` URL into
`FLAG_ENDPOINT` in `index.html` (and `TESTER_KEY` if you set `KEY`), and add
`COLLECTOR_URL` (+ optional `COLLECTOR_KEY`) as repo Action secrets.

## The chain (decided: batched GitHub Action)

```
app: flag + record the correct       →  collector (Google Apps Script)
  pronunciation (clip_id + region)        appends a row to a Google Sheet
                                          + stores the audio (Drive)
                                                   │
review web app: a native speaker plays the AI original (its public Pages URL)
  next to the tester's suggestion, and clicks approve  →  approved = TRUE
                                                   │
GitHub Action (batch): reads approved && not-installed rows, fetches each
  recording, ffmpeg-processes it, writes audio/<region>/<clip_id>.mp3,
  commits + pushes, marks installed = TRUE
```

Approvals queue in the Sheet; a batch run installs everything approved since
last time. Trigger the Action manually (workflow_dispatch), on a schedule, or
from a "run batch" button in the review app (repository_dispatch).

## Key design constraint (the important one)

**Every recording is tagged with its accent.** A recording carries both:

- `clip_id` — which syllable it corrects
- `region` — `south` or `north`

so an approved **Southern** recording replaces `audio/south/<clip_id>.mp3` and
**not** the Northern clip. `install_approved.py` already reads a `region` field and
writes to `audio/<region>/`, so the installer side is ready; the record UI must
capture the accent that was active when the user recorded (the app already knows it
as `S.cfg.region`).

## To build later — four pieces

1. **Record + flag UI in `index.html`** — a flag button on a clip, a recorder, and a
   send action. Post `clip_id`, `region`, `syllable`, and the audio to the collector.
   (Reference the old `Index.html` in git history for the interaction, but rebuild it
   against the current single-file app and the south/north accent model.)
2. **Collector** — a Google Apps Script web app that appends a row to a Google Sheet
   and stores the audio. The Sheet has status columns: `approved` (reviewer sets) and
   `installed` (the Action sets). It must also expose the approved rows and a
   **downloadable URL (or base64) for each recording's audio**, so the Action can
   fetch it — this is the one change from the Colab version, which read files off a
   mounted Drive folder. Optional shared `KEY` to stop random posts.
3. **Review web app** — lists rows where `approved` is unset; for each, plays the AI
   original from its Pages URL (`audio/<region>/<clip_id>.mp3`) and the tester's
   suggestion; approve/reject buttons set `approved`.
4. **GitHub Action (batch)** — reuses `install_approved.py`'s logic (same ffmpeg
   filter, same per-region install). On `workflow_dispatch`/schedule it reads
   approved && not-installed rows, fetches each recording by URL, processes it,
   writes `audio/<region>/<clip_id>.mp3`, commits and pushes with the built-in
   `GITHUB_TOKEN` (no extra credentials needed), and marks the rows `installed`.

Nothing here blocks shipping the AI voices — human recordings replace individual
clips by `clip_id` + `region` whenever a batch runs.
