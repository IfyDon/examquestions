from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen


URL = "https://en.wikipedia.org/wiki/Main_Page"
OUTPUT_FILE = Path(__file__).with_name("wikiWebSafe.txt")


class MainPageTextParser(HTMLParser):
    BLOCK_TAGS = {
        "br", "div", "h1", "h2", "h3", "h4", "h5", "h6",
        "li", "p", "section", "td", "th", "tr",
    }
    IGNORED_TAGS = {"script", "style", "noscript"}

    def __init__(self):
        super().__init__()
        self.in_content = False
        self.div_depth = 0
        self.ignored_depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if not self.in_content:
            if tag == "div" and attributes.get("id") == "mw-content-text":
                self.in_content = True
                self.div_depth = 1
            return

        if tag == "div":
            self.div_depth += 1
        if tag in self.IGNORED_TAGS:
            self.ignored_depth += 1
        elif self.ignored_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if not self.in_content:
            return

        if tag in self.IGNORED_TAGS and self.ignored_depth:
            self.ignored_depth -= 1
        elif self.ignored_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

        if tag == "div":
            self.div_depth -= 1
            if self.div_depth == 0:
                self.in_content = False

    def handle_data(self, data):
        if self.in_content and self.ignored_depth == 0:
            self.parts.append(data)

    def get_text(self):
        lines = (" ".join(line.split()) for line in "".join(self.parts).splitlines())
        return "\n".join(line for line in lines if line)


def main():
    request = Request(
        URL,
        headers={"User-Agent": "wikiWebSafe/1.0 (educational scraper; Python urllib)"},
    )
    with urlopen(request, timeout=30) as response:
        page = response.read().decode(response.headers.get_content_charset() or "utf-8")

    parser = MainPageTextParser()
    parser.feed(page)
    text = parser.get_text()
    if not text:
        raise RuntimeError("No page text found in the Wikipedia main-page content.")

    OUTPUT_FILE.write_text(text + "\n", encoding="utf-8")
    print(f"Saved Wikipedia main-page text to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
