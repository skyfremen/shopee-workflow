from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from .media import MediaCandidate


class UnsupportedMediaError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DownloadResult:
    path: Path
    sha256: str
    bytes: int


def _request_headers(
    referer: str,
    user_agent: str,
    cookie_header: str,
) -> dict[str, str]:
    headers = {
        "Referer": referer,
        "User-Agent": user_agent,
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
    return headers


def _download_mp4(
    url: str,
    output_path: Path,
    headers: dict[str, str],
) -> None:
    with httpx.Client(
        headers=headers,
        follow_redirects=True,
        timeout=120.0,
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with output_path.open("wb") as output:
                for chunk in response.iter_bytes():
                    output.write(chunk)


def _assert_unencrypted_hls(
    client: httpx.Client,
    playlist_url: str,
) -> None:
    pending = [playlist_url]
    visited: set[str] = set()

    while pending:
        current_url = pending.pop()
        if current_url in visited:
            continue
        visited.add(current_url)

        if len(visited) > 20:
            raise UnsupportedMediaError("HLS playlist graph is too large for the PoC")

        response = client.get(current_url)
        response.raise_for_status()
        text = response.text.upper()

        if "#EXT-X-KEY" in text or "#EXT-X-SESSION-KEY" in text:
            raise UnsupportedMediaError("encrypted HLS is not supported")

        for raw_line in response.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            child_url = urljoin(current_url, line)
            if urlparse(child_url).path.lower().endswith(".m3u8"):
                pending.append(child_url)


def _download_hls(
    url: str,
    output_path: Path,
    headers: dict[str, str],
) -> None:
    with httpx.Client(
        headers=headers,
        follow_redirects=True,
        timeout=60.0,
    ) as client:
        _assert_unencrypted_hls(client, url)

    ffmpeg_headers = "".join(
        f"{name}: {value}\r\n"
        for name, value in headers.items()
        if name.lower() != "user-agent"
    )

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-user_agent",
        headers["User-Agent"],
    ]

    if ffmpeg_headers:
        command.extend(["-headers", ffmpeg_headers])

    command.extend(
        [
            "-i",
            url,
            "-c",
            "copy",
            str(output_path),
        ]
    )

    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or "ffmpeg failed").strip()
        raise RuntimeError(message[-2_000:]) from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_media(
    candidate: MediaCandidate,
    output_path: Path,
    referer: str,
    user_agent: str,
    cookie_header: str,
) -> DownloadResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = _request_headers(referer, user_agent, cookie_header)

    if candidate.media_type == "mp4":
        _download_mp4(candidate.url, output_path, headers)
    elif candidate.media_type == "hls":
        _download_hls(candidate.url, output_path, headers)
    else:
        raise UnsupportedMediaError(
            f"unsupported media type: {candidate.media_type}"
        )

    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError("download produced an empty output file")

    return DownloadResult(
        path=output_path,
        sha256=_sha256(output_path),
        bytes=output_path.stat().st_size,
    )
