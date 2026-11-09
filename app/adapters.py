import hashlib
import json
import mimetypes
import os
import re
import tempfile
import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.schemas import QuestionInput

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURE_URL = re.compile(r"^fixture://questions/([a-z0-9-]+)$")
JAMB_BASE_URL = "https://jambcbt.awajis.com"
JAMB_HOST = "jambcbt.awajis.com"
JAMB_AJAX_URL = f"{JAMB_BASE_URL}/wp-admin/admin-ajax.php"
USER_AGENT = "wikiWebSafe/1.0 (authorized question-bank import)"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/data/media")).resolve()
IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}
MAX_MEDIA_BYTES = 10 * 1024 * 1024


class SourceAdapter(Protocol):
    def read_questions(self, url: str) -> list[QuestionInput]: ...


class FixtureAdapter:
    def read_question(self, url: str) -> QuestionInput:
        match = FIXTURE_URL.fullmatch(url)
        if not match:
            raise ValueError("The fixture adapter only accepts fixture:// URLs.")

        fixture_path = (FIXTURE_DIR / f"{match.group(1)}.json").resolve()
        if fixture_path.parent != FIXTURE_DIR.resolve():
            raise ValueError("Invalid fixture path.")
        if not fixture_path.is_file():
            raise FileNotFoundError(f"No local fixture for {url}.")

        with fixture_path.open(encoding="utf-8") as fixture_file:
            return QuestionInput.model_validate(json.load(fixture_file))

    def read_questions(self, url: str) -> list[QuestionInput]:
        return [self.read_question(url)]


class AwajisJambAdapter:
    def __init__(self, min_request_interval: float = 1.0):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.min_request_interval = min_request_interval
        self.last_request_at = 0.0
        self.robot_parser = urllib.robotparser.RobotFileParser()
        self.robots_loaded = False
        self.robots_text = ""

    @staticmethod
    def _is_allowed_host(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme == "https" and parsed.hostname == JAMB_HOST

    def _load_robots(self) -> None:
        if self.robots_loaded:
            return
        response = self.session.get(f"{JAMB_BASE_URL}/robots.txt", timeout=20)
        response.raise_for_status()
        self.robots_text = response.text
        self.robot_parser.set_url(f"{JAMB_BASE_URL}/robots.txt")
        self.robot_parser.parse(self.robots_text.splitlines())
        self.robots_loaded = True

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        if not self._is_allowed_host(url):
            raise ValueError(f"Refusing to fetch URL outside {JAMB_HOST}: {url}")

        self._load_robots()
        if not self.robot_parser.can_fetch(USER_AGENT, url):
            raise PermissionError(f"robots.txt disallows fetching {url}")

        elapsed = time.monotonic() - self.last_request_at
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)

        response = self.session.request(method, url, timeout=30, **kwargs)
        self.last_request_at = time.monotonic()
        response.raise_for_status()
        if not self._is_allowed_host(response.url):
            raise ValueError(f"Refusing redirected URL outside {JAMB_HOST}: {response.url}")
        return response

    @staticmethod
    def _xml_locations(content: bytes) -> list[str]:
        root = ET.fromstring(content)
        sitemap_namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        return [
            element.text.strip()
            for element in root.iter()
            if element.tag in {"loc", f"{sitemap_namespace}loc"}
            and element.text
            and element.text.strip()
        ]

    def discover_subject_urls(self) -> list[str]:
        self._load_robots()
        sitemap_urls = [
            line.split(":", 1)[1].strip()
            for line in self.robots_text.splitlines()
            if line.strip().lower().startswith("sitemap:")
        ]
        sitemap_urls.append(f"{JAMB_BASE_URL}/sitemap_index.xml")

        pages = set()
        visited_sitemaps = set()
        while sitemap_urls:
            sitemap_url = sitemap_urls.pop()
            if sitemap_url in visited_sitemaps:
                continue
            visited_sitemaps.add(sitemap_url)
            if not self._is_allowed_host(sitemap_url):
                raise ValueError(f"Refusing sitemap outside {JAMB_HOST}: {sitemap_url}")

            response = self._request("GET", sitemap_url)
            for location in self._xml_locations(response.content):
                if location.lower().endswith(".xml"):
                    sitemap_urls.append(location)
                elif self._is_allowed_host(location):
                    path = urlparse(location).path.rstrip("/")
                    if path and path != "/offline" and not path.startswith("/offline/"):
                        pages.add(location)

        return sorted(pages)

    @staticmethod
    def _quiz_id(page: BeautifulSoup) -> str:
        for field in page.select('input[name="quiz_id"]'):
            if field.get("value", "").isdigit():
                return field["value"]

        match = re.search(
            r"\bquizId\s*:\s*['\"]?(\d+)",
            str(page),
        )
        if match:
            return match.group(1)
        raise ValueError("No public WP Pro Quiz ID found on the subject page.")

    @staticmethod
    def _node_text(node) -> str:
        text = node.get_text(" ", strip=True)
        if text:
            return text
        return " ".join(
            image.get("alt", "").strip()
            for image in node.select("img[alt]")
            if image.get("alt", "").strip()
        )

    @staticmethod
    def _subject_name(page: BeautifulSoup, url: str) -> str:
        meta = page.select_one('meta[property="og:title"]')
        if meta and meta.get("content", "").strip():
            return meta["content"].strip()
        slug = urlparse(url).path.strip("/").split("/")[-1]
        return " ".join(part.upper() if len(part) <= 2 else part.title() for part in slug.split("-"))

    def _download_image(self, source_url: str, alt_text: str) -> dict:
        digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
        suffix = Path(urlparse(source_url).path).suffix.lower()
        allowed_suffixes = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
        extension = suffix if suffix in allowed_suffixes else ""
        relative_path = Path(digest[:2]) / f"{digest}{extension}"
        destination = MEDIA_ROOT / relative_path
        if extension and destination.is_file():
            return {
                "source_url": source_url,
                "media_type": mimetypes.guess_type(source_url)[0] or "application/octet-stream",
                "local_path": relative_path.as_posix(),
                "svg_metadata": {"alt": alt_text} if alt_text else {},
            }

        if not self._is_allowed_host(source_url):
            return {
                "source_url": source_url,
                "media_type": mimetypes.guess_type(source_url)[0] or "application/octet-stream",
                "local_path": None,
                "svg_metadata": {"alt": alt_text} if alt_text else {},
            }

        response = self._request("GET", source_url, stream=True)
        media_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if media_type not in IMAGE_TYPES:
            response.close()
            return {
                "source_url": source_url,
                "media_type": media_type or mimetypes.guess_type(source_url)[0] or "application/octet-stream",
                "local_path": None,
                "svg_metadata": {"alt": alt_text} if alt_text else {},
            }

        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_MEDIA_BYTES:
            response.close()
            raise ValueError(f"Image exceeds the {MAX_MEDIA_BYTES}-byte size limit.")

        extension = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
        }[media_type]
        relative_path = Path(digest[:2]) / f"{digest}{extension}"
        destination = MEDIA_ROOT / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)

        if not destination.exists():
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=destination.parent, prefix=".download-", delete=False
                ) as temp_file:
                    temp_path = Path(temp_file.name)
                    size = 0
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        size += len(chunk)
                        if size > MAX_MEDIA_BYTES:
                            raise ValueError(
                                f"Image exceeds the {MAX_MEDIA_BYTES}-byte size limit."
                            )
                        temp_file.write(chunk)
                temp_path.replace(destination)
            finally:
                response.close()
                if temp_path and temp_path.exists():
                    temp_path.unlink()
        else:
            response.close()

        return {
            "source_url": source_url,
            "media_type": media_type,
            "local_path": relative_path.as_posix(),
            "svg_metadata": {"alt": alt_text} if alt_text else {},
        }

    def _extract_media(self, nodes: list, page_url: str) -> list[dict]:
        media = {}
        for node in nodes:
            for image in node.select("img"):
                image_url = image.get("src") or image.get("data-src")
                if not image_url:
                    continue
                source_url = urljoin(page_url, image_url)
                if urlparse(source_url).scheme not in {"http", "https"}:
                    continue
                if source_url not in media:
                    media[source_url] = self._download_image(
                        source_url, image.get("alt", "").strip()
                    )
        return list(media.values())

    def _parse_quiz_content(
        self, page_url: str, page: BeautifulSoup, content: str
    ) -> list[QuestionInput]:
        quiz = BeautifulSoup(content, "html.parser")
        subject = self._subject_name(page, page_url)
        questions = []
        for item in quiz.select("li.wpProQuiz_listItem"):
            question_node = item.select_one(".wpProQuiz_question_text")
            question_text = self._node_text(question_node) if question_node else ""
            if not question_text:
                continue

            option_items = item.select(".wpProQuiz_questionListItem")
            options = {}
            for index, option_item in enumerate(option_items):
                option_node = option_item.select_one("label") or option_item
                option_text = self._node_text(option_node)
                if option_text:
                    options[chr(ord("A") + index)] = option_text

            media_nodes = [question_node, *option_items]
            questions.append(
                QuestionInput(
                    exam="JAMB",
                    subject=subject,
                    question=question_text,
                    options=options,
                    source_url=page_url,
                    media=self._extract_media(media_nodes, page_url),
                )
            )
        return questions

    def read_questions(self, url: str) -> list[QuestionInput]:
        if not self._is_allowed_host(url):
            raise ValueError(f"Refusing to crawl URL outside {JAMB_HOST}: {url}")

        page_response = self._request("GET", url)
        page = BeautifulSoup(page_response.text, "html.parser")
        if not page.select_one(".wpProQuiz_content"):
            return []
        quiz_id = self._quiz_id(page)
        response = self._request(
            "POST",
            JAMB_AJAX_URL,
            headers={"Referer": page_response.url},
            data={
                "action": "wp_pro_quiz_admin_ajax",
                "func": "quizLoadData",
                "data[quizId]": quiz_id,
                "data[proto]": "3",
            },
        )
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
            raise ValueError(f"The quiz endpoint returned an unexpected response for {url}.")

        return self._parse_quiz_content(
            page_response.url, page, payload["content"]
        )
