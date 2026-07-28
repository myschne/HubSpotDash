from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urlparse
import re


LINK_FIELDS = {"href", "link", "destination", "url"}
SKIPPED_ASSET_EXTENSIONS = {
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
}
SKIPPED_POSITION_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "x.com",
    "youtube.com",
}


class HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.urls.append(value)


class LinkTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self.all_chunks: list[str] = []
        self.current_href = ""
        self.current_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.current_href = value
                self.current_chunks = []
                return

    def handle_data(self, data: str) -> None:
        text = clean_text(data)
        if not text:
            return
        self.all_chunks.append(text)
        if self.current_href:
            self.current_chunks.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self.current_href:
            return
        self.links.append(
            {
                "url": self.current_href,
                "title": clean_text(" ".join(self.current_chunks)),
                "widget_text": clean_text(" ".join(self.all_chunks)),
            }
        )
        self.current_href = ""
        self.current_chunks = []


def link_positions(email: dict[str, Any]) -> dict[str, int]:
    content = email.get("content", {})
    if isinstance(content, dict) and isinstance(content.get("widgets"), dict):
        ordered = unique_links(extract_widget_links(content["widgets"]))
    else:
        ordered = unique_links(extract_links(content))
    return {canonical_url(url): index for index, url in enumerate(ordered, start=1)}


def link_metadata(email: dict[str, Any]) -> dict[str, dict[str, str | int]]:
    positions = link_positions(email)
    metadata = {
        key: {"position": position, "title": "", "blurb": ""}
        for key, position in positions.items()
    }
    content = email.get("content", {})
    widgets = content.get("widgets", {}) if isinstance(content, dict) else {}
    if isinstance(widgets, dict):
        for widget_key in sorted(widgets, key=natural_widget_key):
            for item in extract_widget_metadata(widgets[widget_key]):
                key = canonical_url(item["url"])
                if not key or key not in metadata:
                    continue
                title = clean_text(item.get("title", ""))
                widget_text = clean_text(item.get("widget_text", ""))
                if title and not metadata[key]["title"]:
                    metadata[key]["title"] = title
                if widget_text and not metadata[key]["blurb"]:
                    metadata[key]["blurb"] = blurb_from_widget_text(widget_text, title)
    return metadata


def extract_widget_metadata(widget: Any) -> list[dict[str, str]]:
    if not isinstance(widget, dict):
        return []
    body = widget.get("body", {})
    html = body.get("html") if isinstance(body, dict) else None
    if not isinstance(html, str) or "href" not in html.lower():
        return []

    parser = LinkTextParser()
    parser.feed(html)
    return [
        item
        for item in parser.links
        if should_include_position_link(item.get("url", ""))
    ]


def extract_widget_links(widgets: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for widget_key in sorted(widgets, key=natural_widget_key):
        links.extend(extract_links(widgets[widget_key], widget_key))
    return links


def natural_widget_key(value: str) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", value)
    ]


def extract_links(value: Any, key: str = "") -> list[str]:
    links: list[str] = []
    key_lower = key.lower()

    if isinstance(value, dict):
        for child_key, child_value in value.items():
            links.extend(extract_links(child_value, str(child_key)))
        return links

    if isinstance(value, list):
        for item in value:
            links.extend(extract_links(item, key))
        return links

    if not isinstance(value, str):
        return links

    if "<a " in value.lower() and "href" in value.lower():
        parser = HrefParser()
        parser.feed(value)
        links.extend(parser.urls)
    elif key_lower in LINK_FIELDS and value.startswith(("http://", "https://")):
        links.append(value)

    return [link for link in links if should_include_position_link(link)]


def unique_links(links: list[str]) -> list[str]:
    seen = set()
    unique = []
    for link in links:
        key = canonical_url(link)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(link)
    return unique


def canonical_url(url: str) -> str:
    parsed = urlparse(str(url).strip())
    if not parsed.netloc:
        return ""
    path = unquote(parsed.path).rstrip("/")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower().removeprefix('www.')}{path}".rstrip("/")


def should_include_position_link(url: str) -> bool:
    parsed = urlparse(str(url).strip())
    if not parsed.netloc:
        return False
    domain = parsed.netloc.lower().removeprefix("www.")
    if domain in SKIPPED_POSITION_DOMAINS:
        return False
    if domain.endswith("advancedmanufacturing.org") and parsed.path.rstrip("/").endswith("/advertise"):
        return False
    path_lower = parsed.path.lower()
    if any(path_lower.endswith(extension) for extension in SKIPPED_ASSET_EXTENSIONS):
        return False
    return True


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def blurb_from_widget_text(widget_text: str, title: str) -> str:
    if title and widget_text.lower().startswith(title.lower()):
        return clean_text(widget_text[len(title):])
    return widget_text
