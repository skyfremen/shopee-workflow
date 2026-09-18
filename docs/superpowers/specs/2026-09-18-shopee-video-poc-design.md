# Shopee Video Downloader PoC — Design

**Date:** 2026-09-18  
**Repository:** `skyfremen/shopee-workflow`  
**Status:** Proposed PoC architecture

## Goal

Prove that a GitHub-hosted runner can open a public Shopee product/video URL in a real browser, observe the media requests required for normal playback, identify an ordinary MP4 or HLS source, download the media, and publish the result as a GitHub Actions artifact.

This PoC is intentionally narrow. It is a media-extraction experiment, not a general Shopee crawler.

## Scope

### Included

- Manual `workflow_dispatch` trigger.
- One Shopee URL per run.
- Ubuntu GitHub-hosted runner.
- Python 3.
- Playwright + Chromium.
- Network-response observation for:
  - `video/*` responses
  - `.mp4` URLs
  - ordinary `.m3u8` HLS playlists
- Direct MP4 download.
- Ordinary, unencrypted HLS remux through FFmpeg.
- Metadata output describing the source page and selected media.
- SHA-256 of the downloaded media.
- GitHub Actions artifact containing the media and metadata.
- Diagnostic JSON when no usable media is found.

### Explicitly excluded

- Shopee login automation.
- CAPTCHA solving.
- Proxy rotation or stealth/anti-bot bypass.
- DRM/encrypted-stream circumvention.
- Private or authenticated API reverse engineering.
- Site-wide crawling or seller discovery.
- Automated reposting/uploading.
- Long-term storage in Git.
- Affiliate/API integration.
- Unit-test suite.
- README/documentation beyond this design spec.

If normal public access is blocked, the run fails with a useful diagnostic rather than attempting to bypass the restriction.

## Architecture

```text
workflow_dispatch(url)
        |
        v
validate input URL
        |
        v
Playwright / Chromium
        |
        +--> open public Shopee page
        |
        +--> observe response URLs + content types
        |
        v
Media candidate collector
        |
        +--> MP4 candidates
        +--> HLS candidates
        |
        v
Deterministic media selector
        |
        v
Downloader
   +----+----+
   |         |
 MP4       HLS
 HTTP      FFmpeg
   |         |
   +----+----+
        |
        v
output/
  video.mp4
  metadata.json
        |
        v
actions/upload-artifact
```

## Repository layout

```text
shopee-workflow/
├── .github/
│   └── workflows/
│       └── poc-download.yml
├── src/
│   └── shopee_poc/
│       ├── __init__.py
│       ├── cli.py
│       ├── browser.py
│       ├── media.py
│       └── download.py
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-09-18-shopee-video-poc-design.md
├── requirements.txt
└── .gitignore
```

## Component responsibilities

### `cli.py`

Owns orchestration only:

1. Validate the supplied URL.
2. Start browser discovery.
3. Select the best supported media candidate.
4. Download/remux it.
5. Write metadata.
6. Exit non-zero on failure.

It does not contain Shopee page selectors or media-selection logic.

### `browser.py`

Owns browser interaction.

- Launches headless Chromium.
- Opens the supplied public page.
- Attaches response listeners before navigation.
- Records candidate media responses.
- Also inspects rendered `<video>` and `<source>` elements after page load.
- Uses bounded timeouts.
- Returns candidates and limited diagnostics.

No login state is persisted.

### `media.py`

Pure deterministic logic.

Normalizes and ranks candidates. Initial preference:

1. Direct MP4.
2. Ordinary HLS playlist.
3. Unsupported candidates are ignored.

Duplicate URLs are collapsed.

### `download.py`

Handles media retrieval.

- MP4: streamed HTTP download.
- HLS: FFmpeg remux to MP4.
- Rejects unsupported/encrypted/DRM cases.
- Computes SHA-256 after a successful download.

## Metadata contract

Example `output/metadata.json`:

```json
{
  "schema_version": 1,
  "page_url": "https://shopee.sg/...",
  "media_url": "https://...",
  "media_type": "mp4",
  "downloaded_at": "2026-09-18T12:00:00Z",
  "sha256": "...",
  "bytes": 1234567
}
```

The PoC keeps the contract small so a future production workflow can consume the output without depending on scraper internals.

## GitHub Actions workflow

The first workflow is manual only:

```text
workflow_dispatch
    input: url
       |
       v
checkout
       |
setup-python
       |
install Python requirements
       |
install Playwright Chromium
       |
verify FFmpeg
       |
run PoC downloader
       |
upload output/ as artifact
```

A scheduled crawler is deliberately not part of the PoC. Scheduling should be considered only after confirming that the GitHub-hosted runner can consistently access the target public pages.

## Error handling

The CLI will use distinct failure reasons so workflow logs remain useful:

- `invalid_url`
- `navigation_failed`
- `blocked_or_challenged`
- `no_media_found`
- `unsupported_media`
- `download_failed`

When practical, a small diagnostic JSON file should still be written and uploaded on failure. The PoC should not store page cookies or secrets in diagnostics.

## PoC validation

There is no unit-test suite in this PoC.

The live GitHub Action is the validation mechanism. A successful run must produce an artifact containing `video.mp4` and `metadata.json`.

## PoC success criteria

The PoC is successful when all of the following are true:

1. A user can manually trigger the workflow with one public Shopee URL.
2. The workflow runs entirely on `ubuntu-latest`.
3. At least one public URL exposing ordinary media can produce a playable `video.mp4`.
4. `metadata.json` records the originating page URL, selected media URL/type, file size, timestamp, and SHA-256.
5. The result is available as a GitHub Actions artifact.
6. A blocked, challenged, or media-less page fails cleanly without bypass behavior.

## Future phases, only after PoC validation

Possible later additions:

- Queue/batch input.
- De-duplication state.
- Scheduled execution.
- Product discovery through an approved source.
- Downstream video transformation.
- External object storage.
- Analytics and affiliate-link generation.

These are intentionally deferred so the first experiment answers the main uncertainty: **can a normal GitHub-hosted Chromium runner retrieve a usable public Shopee video reliably enough to build on?**
