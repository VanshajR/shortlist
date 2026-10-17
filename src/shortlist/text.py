"""Job descriptions arrive as HTML from most boards. Everything downstream
(filters, embeddings, the LLM judge, Telegram) wants plain text."""
import html
import re
from html.parser import HTMLParser

BLOCK = {"p", "div", "br", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "section", "tr", "table"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK or tag == "li":
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    if "<" not in raw:
        return _tidy(html.unescape(raw))
    parser = _Text()
    parser.feed(raw)
    parser.close()
    # every block tag opens and closes a line, so blank lines here are noise
    return re.sub(r"\n{2,}", "\n", _tidy("".join(parser.parts)))


def _tidy(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n- *\n", "\n- ", text)       # a bullet whose text sat in a <p>
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
