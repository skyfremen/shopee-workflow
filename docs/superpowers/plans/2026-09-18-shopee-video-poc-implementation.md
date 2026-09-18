# Shopee Video Downloader PoC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal GitHub Actions PoC that accepts one public Shopee URL, detects normally served MP4/HLS media with Playwright, downloads it, and uploads the result plus metadata as an Actions artifact.

**Architecture:** A manual GitHub Action runs Python on `ubuntu-latest`. Playwright opens the public Shopee page and observes media responses; deterministic selection prefers MP4 over ordinary HLS; the downloader streams MP4 directly or remuxes unencrypted HLS with FFmpeg; the CLI writes `video.mp4`, `metadata.json`, or a failure diagnostic.

**Tech Stack:** GitHub Actions, Python 3.12, Playwright/Chromium, httpx, FFmpeg.

**Spec:** `docs/superpowers/specs/2026-09-18-shopee-video-poc-design.md`

## Global Constraints

- Manual `workflow_dispatch` only.
- One Shopee URL per run.
- Run on `ubuntu-latest`.
- No login automation.
- No CAPTCHA solving.
- No proxy rotation or stealth/anti-bot bypass.
- No DRM/encrypted-stream circumvention.
- No private/authenticated Shopee API reverse engineering.
- No site-wide crawling.
- No automated reposting/uploading.
- No unit-test suite or README for this PoC.
- Live workflow execution is the integration validation.

---

### Task 1: Add Python package skeleton and media model

**Files:**
- Create: `src/shopee_poc/__init__.py`
- Create: `src/shopee_poc/media.py`
- Create: `requirements.txt`
- Create: `.gitignore`

**Interfaces:**
- Produces: `MediaCandidate(url: str, media_type: str, content_type: str = "", source: str = "")`
- Produces: `classify_media(url: str, content_type: str) -> str | None`
- Produces: `select_candidate(candidates: list[MediaCandidate]) -> MediaCandidate | None`

- [ ] **Step 1: Add dependencies and ignore generated output**

`requirements.txt`:

```text
playwright==1.55.0
httpx==0.28.1
```

`.gitignore`:

```text
__pycache__/
*.py[cod]
.venv/
output/
```

- [ ] **Step 2: Add package marker**

`src/shopee_poc/__init__.py` contains only a short module docstring.

- [ ] **Step 3: Implement deterministic media classification and selection**

`src/shopee_poc/media.py` defines the dataclass and functions above. Classification rules:

- `video/mp4` or URL path ending `.mp4` => `mp4`
- HLS MIME types or URL path ending `.m3u8` => `hls`
- anything else => unsupported
- de-duplicate by exact URL
- prefer MP4 over HLS
- preserve first-seen ordering within the same media type

- [ ] **Step 4: Verify syntax**

Run:

```bash
python -m compileall -q src
```

Expected: exit code 0.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore src/shopee_poc/__init__.py src/shopee_poc/media.py
git commit -m "feat: add Shopee PoC media model"
```

---

### Task 2: Add Playwright public-page media discovery

**Files:**
- Create: `src/shopee_poc/browser.py`

**Interfaces:**
- Consumes: `MediaCandidate`, `classify_media`
- Produces: `DiscoveryResult(candidates, final_url, title, status_code, blocked, user_agent, cookie_header)`
- Produces: `async discover_media(page_url: str) -> DiscoveryResult`

- [ ] **Step 1: Implement browser discovery**

Launch Chromium headless with a normal viewport and `en-SG` locale. Attach a response listener before navigation. Record a candidate whenever its URL/content-type is classified as MP4 or HLS.

Navigate with:

```python
await page.goto(page_url, wait_until="domcontentloaded", timeout=60_000)
```

Then:

1. wait briefly for lazy loading,
2. scroll once to trigger normal page media loading,
3. inspect `video` and nested `source` elements,
4. call `play()` on rendered videos while muted to allow normal playback requests,
5. wait again for media network traffic.

Collect the browser user-agent and context cookies for the later downloader, but never persist cookies to metadata or diagnostics.

- [ ] **Step 2: Detect obvious block/challenge pages without bypassing them**

Mark `blocked=True` if the page title/body contains common challenge indicators such as `captcha`, `verify you are human`, `access denied`, `unusual traffic`, or `robot`.

- [ ] **Step 3: Verify syntax**

Run:

```bash
python -m compileall -q src
```

Expected: exit code 0.

- [ ] **Step 4: Commit**

```bash
git add src/shopee_poc/browser.py
git commit -m "feat: discover public Shopee media with Playwright"
```

---

### Task 3: Add MP4/HLS downloader

**Files:**
- Create: `src/shopee_poc/download.py`

**Interfaces:**
- Consumes: `MediaCandidate`
- Produces: `DownloadResult(path: Path, sha256: str, bytes: int)`
- Produces: `download_media(candidate, output_path, referer, user_agent, cookie_header) -> DownloadResult`

- [ ] **Step 1: Implement shared request headers**

Use only the public page context:

```python
{
    "Referer": referer,
    "User-Agent": user_agent,
    "Cookie": cookie_header
}
```

Omit the Cookie header when empty.

- [ ] **Step 2: Implement direct MP4 streaming**

Use `httpx.Client(follow_redirects=True, timeout=120)` and stream bytes directly to `output/video.mp4` rather than buffering the whole file in memory.

- [ ] **Step 3: Implement ordinary HLS handling**

Before invoking FFmpeg, fetch the selected playlist with the same headers.

Reject it as unsupported if it contains `#EXT-X-KEY`; do not attempt decryption.

For an ordinary playlist, call FFmpeg with the public request headers and:

```text
-c copy
```

to remux to MP4.

- [ ] **Step 4: Compute result metadata**

After a successful MP4/HLS download:

- compute SHA-256,
- read file size,
- return `DownloadResult`.

- [ ] **Step 5: Verify syntax**

Run:

```bash
python -m compileall -q src
```

Expected: exit code 0.

- [ ] **Step 6: Commit**

```bash
git add src/shopee_poc/download.py
git commit -m "feat: download public MP4 and HLS media"
```

---

### Task 4: Add CLI orchestration and diagnostics

**Files:**
- Create: `src/shopee_poc/cli.py`

**Interfaces:**
- Consumes: `discover_media`, `select_candidate`, `download_media`
- Produces command: `python -m shopee_poc.cli <url>`
- Produces files: `output/video.mp4`, `output/metadata.json`, or `output/diagnostic.json`

- [ ] **Step 1: Validate input URL**

Accept only HTTPS URLs whose hostname is `shopee.sg` or a subdomain ending in `.shopee.sg`.

Invalid input writes:

```json
{"error":"invalid_url"}
```

and exits non-zero.

- [ ] **Step 2: Orchestrate discovery**

If Playwright navigation fails, write `navigation_failed`.

If `DiscoveryResult.blocked` is true, write `blocked_or_challenged`.

If no supported candidate is found, write `no_media_found`.

Diagnostics may include safe fields such as final URL, title, HTTP status, and discovered candidate count. Do not include cookies.

- [ ] **Step 3: Download selected media**

Create `output/`, download to `output/video.mp4`, and convert downloader exceptions into:

- `unsupported_media`
- `download_failed`

- [ ] **Step 4: Write successful metadata**

Write `output/metadata.json` with:

```json
{
  "schema_version": 1,
  "page_url": "<input>",
  "final_url": "<browser final URL>",
  "media_url": "<selected URL>",
  "media_type": "mp4",
  "downloaded_at": "<UTC ISO-8601>",
  "sha256": "<hex>",
  "bytes": 123
}
```

- [ ] **Step 5: Verify import and argument parsing**

Run:

```bash
PYTHONPATH=src python -m shopee_poc.cli
```

Expected: non-zero exit with usage text and no Python traceback caused by import errors.

Run:

```bash
PYTHONPATH=src python -m shopee_poc.cli "https://example.com/"
```

Expected: non-zero exit and `output/diagnostic.json` containing `invalid_url`.

- [ ] **Step 6: Commit**

```bash
git add src/shopee_poc/cli.py
git commit -m "feat: add Shopee PoC CLI orchestration"
```

---

### Task 5: Add manual GitHub Actions workflow

**Files:**
- Create: `.github/workflows/poc-download.yml`

**Interfaces:**
- Consumes: required `workflow_dispatch.inputs.url`
- Produces: Actions artifact `shopee-poc-output`

- [ ] **Step 1: Define manual trigger**

Use a single required string input named `url`.

- [ ] **Step 2: Define runner setup**

Use:

- `ubuntu-latest`
- `actions/checkout@v4`
- `actions/setup-python@v5` with Python `3.12`
- `pip install -r requirements.txt`
- `python -m playwright install --with-deps chromium`
- `ffmpeg -version`

Set `permissions: contents: read`.

- [ ] **Step 3: Run downloader**

Set `PYTHONPATH=src` and execute:

```bash
python -m shopee_poc.cli "${{ inputs.url }}"
```

- [ ] **Step 4: Always upload diagnostics/results**

Use `actions/upload-artifact@v4` with:

- name: `shopee-poc-output`
- path: `output/`
- `if: always()`
- `if-no-files-found: warn`
- short retention suitable for PoC output

- [ ] **Step 5: Validate YAML shape locally**

Parse `.github/workflows/poc-download.yml` with a YAML parser to ensure it is syntactically valid.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/poc-download.yml
git commit -m "ci: add Shopee video PoC workflow"
```

---

### Task 6: Final verification

**Files:**
- Verify all files created by Tasks 1-5.

**Interfaces:**
- Produces a feature branch ready for manual GitHub Actions validation.

- [ ] **Step 1: Compile all Python**

Run:

```bash
python -m compileall -q src
```

Expected: exit code 0.

- [ ] **Step 2: Verify invalid-domain behavior**

Run:

```bash
rm -rf output
PYTHONPATH=src python -m shopee_poc.cli "https://example.com/" || true
cat output/diagnostic.json
```

Expected error value: `invalid_url`.

- [ ] **Step 3: Inspect workflow for intended trigger and artifact behavior**

Confirm:

- manual trigger only,
- one required URL input,
- Python 3.12,
- Playwright Chromium install,
- FFmpeg availability check,
- CLI execution with `PYTHONPATH=src`,
- artifact upload runs with `always()`.

- [ ] **Step 4: Commit any verification-only fixes**

If verification requires code changes, commit only those fixes with a focused message.

- [ ] **Step 5: Do not merge automatically**

Leave `feat/shopee-poc-downloader` ready for the user to manually trigger or review before merging into `main`.
