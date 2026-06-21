import io
import json

import httpx

from sources.museum_nl.adapter import snapshot

SITEMAP = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://www.museum.nl/nl/anne-frank-huis</loc></url>
  <url><loc>https://www.museum.nl/nl/rijksmuseum-amsterdam</loc></url>
</urlset>"""
PAGES = {
    "anne-frank-huis": "<html>afh</html>",
    "rijksmuseum-amsterdam": "<html>rijks</html>",
}


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("sitemap.xml"):
        return httpx.Response(200, text=SITEMAP)
    slug = request.url.path.rsplit("/", 1)[-1]
    return httpx.Response(200, text=PAGES[slug])


def test_snapshot_writes_envelope():
    client = httpx.Client(transport=httpx.MockTransport(_handler))
    buf = io.BytesIO()
    meta = snapshot(buf, client=client, sleep=lambda _: None)

    assert meta.source_id == "museum-nl"
    assert len(meta.checksum) == 64  # sha256 hex
    lines = buf.getvalue().decode("utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert set(first) == {"slug", "url", "html"}
    assert first["slug"] == "anne-frank-huis"  # sorted slug order
    assert first["html"] == "<html>afh</html>"
