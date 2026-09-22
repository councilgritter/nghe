# The collector (Google Apps Script)

This is the middle of the flag pipeline (see `../human-recordings.md`): the Nghe
app POSTs flags and recordings here, a native speaker reviews recordings in a
built-in page, and the approved ones are exposed for the install Action.

Two files:
- **`collector.gs`** — the web app (paste as the script `Code.gs`).
- **`review.html`** — the review page (add as an HTML file named `review`).

## Deploy it

1. Create a **Google Sheet** (any name). This is where flags and recordings are logged.
2. In the Sheet: **Extensions → Apps Script**. This opens a script bound to the Sheet.
3. Replace the default `Code.gs` contents with **`collector.gs`**.
4. **+ → HTML**, name it **`review`** (exactly), and paste in **`review.html`**.
5. Optional: set `KEY` at the top of `collector.gs` to a random string to stop random
   posts. If you do, set the same string as `TESTER_KEY` in `index.html`.
6. Check `PAGES_BASE` points at your site's audio (default is `councilgritter.github.io/nghe/audio`).
7. **Deploy → New deployment → Web app.**
   - **Execute as:** Me
   - **Who has access:** Anyone (so phones can post without signing in)
   - Deploy, authorise the permissions it asks for (Sheets + Drive), and **copy the
     `/exec` URL**.
8. Put that URL in **`index.html`**: set `const FLAG_ENDPOINT = '…/exec';` (and
   `TESTER_KEY` if you set a `KEY`). Commit and push — now flags and recordings flow
   to the Sheet, and the app offers the recording step.

The script creates the `Flags` and `Recordings` tabs and a Drive folder called
**Nghe recordings** the first time it runs.

## Use it

- **Review:** open the `/exec` URL in a browser. You'll see each pending recording with
  the AI original and the tester's version side by side; **Approve** or **Reject**.
  Approve writes `TRUE` in the Recordings tab's `approved` column.
- **Install:** the GitHub Action (next piece) reads `…/exec?approved=1`, fetches each
  approved recording, installs it over `audio/<region>/<clip>.mp3`, pushes, and marks
  the row `installed`.

## What the app sends

- A **flag**: `{clip, syllable, region, reason, when}` → a row in `Flags`.
- A **recording**: `{clip, syllable, region, mime, by, when, audio(base64)}` → the audio
  saved to Drive and a row in `Recordings` (with blank `approved`/`installed`).

Both are tagged with `region` (`south`/`north`), so an approved Southern recording only
ever replaces the Southern clip.

## Redeploying after edits

Apps Script keeps the same `/exec` URL only if you **Deploy → Manage deployments → edit
(pencil) → Version: New version**. A brand-new deployment gives a new URL (which you'd
have to paste into `index.html` again), so prefer editing the existing one.
