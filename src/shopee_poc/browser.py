from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from .media import MediaCandidate, classify_media


_BLOCK_INDICATORS = (
    "captcha",
    "verify you are human",
    "access denied",
    "unusual traffic",
    "robot",
)


@dataclass(slots=True)
class DiscoveryResult:
    candidates: list[MediaCandidate]
    final_url: str
    title: str
    status_code: int | None
    blocked: bool
    user_agent: str
    cookie_header: str


async def discover_media(page_url: str) -> DiscoveryResult:
    candidates: list[MediaCandidate] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                locale="en-SG",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            def on_response(response) -> None:
                try:
                    content_type = response.headers.get("content-type", "")
                    media_type = classify_media(response.url, content_type)
                    if media_type:
                        candidates.append(
                            MediaCandidate(
                                url=response.url,
                                media_type=media_type,
                                content_type=content_type,
                                source="network",
                            )
                        )
                except Exception:
                    # A failed observation must not break normal page loading.
                    return

            page.on("response", on_response)

            try:
                navigation = await page.goto(
                    page_url,
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
            except PlaywrightTimeoutError as exc:
                raise RuntimeError("navigation timed out") from exc

            await page.wait_for_timeout(3_000)

            try:
                await page.evaluate(
                    "() => window.scrollTo(0, Math.floor(document.body.scrollHeight * 0.35))"
                )
            except Exception:
                pass

            await page.wait_for_timeout(2_000)

            try:
                dom_sources = await page.locator("video").evaluate_all(
                    """videos => videos.flatMap(video => [
                        video.currentSrc,
                        video.src,
                        ...Array.from(video.querySelectorAll('source')).map(source => source.src)
                    ]).filter(Boolean)"""
                )
                for source_url in dom_sources:
                    media_type = classify_media(source_url)
                    if media_type:
                        candidates.append(
                            MediaCandidate(
                                url=source_url,
                                media_type=media_type,
                                source="dom",
                            )
                        )
            except Exception:
                pass

            try:
                await page.locator("video").evaluate_all(
                    """videos => {
                        for (const video of videos) {
                            video.muted = true;
                            const attempt = video.play();
                            if (attempt && attempt.catch) {
                                attempt.catch(() => {});
                            }
                        }
                    }"""
                )
            except Exception:
                pass

            await page.wait_for_timeout(5_000)

            title = ""
            try:
                title = await page.title()
            except Exception:
                pass

            body_text = ""
            try:
                body_text = await page.locator("body").inner_text(timeout=5_000)
            except Exception:
                pass

            status_code = navigation.status if navigation else None
            challenge_text = f"{title}\n{body_text[:20_000]}".lower()
            blocked = status_code in {401, 403, 429} or any(
                marker in challenge_text for marker in _BLOCK_INDICATORS
            )

            user_agent = await page.evaluate("() => navigator.userAgent")
            cookies = await context.cookies()
            cookie_header = "; ".join(
                f"{cookie['name']}={cookie['value']}" for cookie in cookies
            )

            return DiscoveryResult(
                candidates=candidates,
                final_url=page.url,
                title=title,
                status_code=status_code,
                blocked=blocked,
                user_agent=user_agent,
                cookie_header=cookie_header,
            )
        finally:
            await browser.close()
