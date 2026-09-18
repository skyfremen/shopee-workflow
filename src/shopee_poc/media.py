from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


_HLS_CONTENT_TYPES = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
}

_MP4_CONTENT_TYPES = {
    "video/mp4",
    "application/mp4",
}


@dataclass(frozen=True, slots=True)
class MediaCandidate:
    url: str
    media_type: str
    content_type: str = ""
    source: str = ""


def classify_media(url: str, content_type: str = "") -> str | None:
    normalized_type = content_type.lower().split(";", 1)[0].strip()
    path = urlparse(url).path.lower()

    if normalized_type in _MP4_CONTENT_TYPES or path.endswith(".mp4"):
        return "mp4"

    if normalized_type in _HLS_CONTENT_TYPES or path.endswith(".m3u8"):
        return "hls"

    return None


def select_candidate(candidates: list[MediaCandidate]) -> MediaCandidate | None:
    seen: set[str] = set()
    unique: list[MediaCandidate] = []

    for candidate in candidates:
        if candidate.url in seen:
            continue
        seen.add(candidate.url)
        unique.append(candidate)

    for preferred_type in ("mp4", "hls"):
        for candidate in unique:
            if candidate.media_type == preferred_type:
                return candidate

    return None
