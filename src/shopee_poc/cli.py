from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .browser import DiscoveryResult, discover_media
from .download import UnsupportedMediaError, download_media
from .media import select_candidate


OUTPUT_DIR = Path("output")


def is_valid_shopee_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False

    hostname = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and (hostname == "shopee.sg" or hostname.endswith(".shopee.sg"))
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _safe_discovery_fields(result: DiscoveryResult) -> dict:
    return {
        "final_url": result.final_url,
        "title": result.title,
        "status_code": result.status_code,
        "candidate_count": len(result.candidates),
    }


def _write_error(error: str, **details) -> None:
    payload = {"error": error}
    payload.update(details)
    _write_json(OUTPUT_DIR / "diagnostic.json", payload)


async def _run(url: str) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not is_valid_shopee_url(url):
        _write_error("invalid_url")
        return 2

    try:
        discovery = await discover_media(url)
    except Exception as exc:
        _write_error(
            "navigation_failed",
            message=str(exc)[:1_000],
        )
        return 3

    safe_fields = _safe_discovery_fields(discovery)

    if discovery.blocked:
        _write_error("blocked_or_challenged", **safe_fields)
        return 4

    candidate = select_candidate(discovery.candidates)
    if candidate is None:
        _write_error("no_media_found", **safe_fields)
        return 5

    output_path = OUTPUT_DIR / "video.mp4"

    try:
        result = download_media(
            candidate=candidate,
            output_path=output_path,
            referer=discovery.final_url or url,
            user_agent=discovery.user_agent,
            cookie_header=discovery.cookie_header,
        )
    except UnsupportedMediaError as exc:
        _write_error(
            "unsupported_media",
            message=str(exc)[:1_000],
            **safe_fields,
        )
        return 6
    except Exception as exc:
        _write_error(
            "download_failed",
            message=str(exc)[:1_000],
            **safe_fields,
        )
        return 7

    diagnostic_path = OUTPUT_DIR / "diagnostic.json"
    if diagnostic_path.exists():
        diagnostic_path.unlink()

    downloaded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _write_json(
        OUTPUT_DIR / "metadata.json",
        {
            "schema_version": 1,
            "page_url": url,
            "final_url": discovery.final_url,
            "media_url": candidate.url,
            "media_type": candidate.media_type,
            "downloaded_at": downloaded_at,
            "sha256": result.sha256,
            "bytes": result.bytes,
        },
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download public video media exposed by a Shopee page."
    )
    parser.add_argument("url", help="Public https://shopee.sg URL")
    args = parser.parse_args()
    return asyncio.run(_run(args.url))


if __name__ == "__main__":
    raise SystemExit(main())
