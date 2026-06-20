from sources.museum_nl.parse import (
    extract_meta_description,
    extract_museum_jsonld,
    extract_slugs,
    normalize_website,
    split_street,
)

SITEMAP = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://www.museum.nl/nl/anne-frank-huis</loc></url>
  <url><loc>https://www.museum.nl/nl/rijksmuseum-amsterdam</loc></url>
  <url><loc>https://www.museum.nl/nl/amsterdam</loc></url>
  <url><loc>https://www.museum.nl/nl/zien-en-doen/musea</loc></url>
  <url><loc>https://www.museum.nl/en/anne-frank-huis</loc></url>
  <url><loc>https://www.museum.nl/nl/anne-frank-huis</loc></url>
</urlset>"""

MUSEUM_HTML = """<html><head>
<meta name="description" content="Een mooi museum.">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Museum","name":"Anne Frank Huis",
 "telephone":"020   55 67 105",
 "address":{"@type":"PostalAddress","streetAddress":"Westermarkt 20",
   "addressLocality":"Amsterdam","postalCode":"1016 DK","addressCountry":"NL"},
 "geo":{"@type":"GeoCoordinates","latitude":52.375083,"longitude":4.884031},
 "sameAs":"www.annefrank.org"}
</script></head><body></body></html>"""

THEME_HTML = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"WebPage","name":"Amsterdam"}
</script></head><body></body></html>"""


def test_extract_slugs_keeps_single_segment_nl_pages():
    assert extract_slugs(SITEMAP) == ["amsterdam", "anne-frank-huis", "rijksmuseum-amsterdam"]


def test_extract_museum_jsonld_returns_museum_node():
    node = extract_museum_jsonld(MUSEUM_HTML)
    assert node is not None and node["name"] == "Anne Frank Huis"
    assert node["geo"]["latitude"] == 52.375083


def test_extract_museum_jsonld_none_for_non_museum():
    assert extract_museum_jsonld(THEME_HTML) is None


def test_extract_meta_description():
    assert extract_meta_description(MUSEUM_HTML) == "Een mooi museum."
    assert extract_meta_description("<html></html>") is None


def test_split_street():
    assert split_street("Westermarkt 20") == ("Westermarkt", "20")
    assert split_street("Museumplein") == ("Museumplein", None)


def test_normalize_website():
    assert normalize_website("www.annefrank.org") == "https://www.annefrank.org"
    assert normalize_website("https://x.nl") == "https://x.nl"
    assert normalize_website(["http://a.nl", "http://b.nl"]) == "http://a.nl"
    assert normalize_website("mailto:x@y.nl") is None
    assert normalize_website(None) is None


def test_normalize_website_empty_list():
    assert normalize_website([]) is None


def test_extract_meta_description_content_before_name():
    # content= appears before name="description" — must still extract correctly
    html = '<html><head><meta content="Reversed order." name="description"></head></html>'
    assert extract_meta_description(html) == "Reversed order."


def test_extract_meta_description_og_fallback():
    # no name="description" — should fall back to og:description
    html = '<html><head><meta property="og:description" content="OG fallback."></head></html>'
    assert extract_meta_description(html) == "OG fallback."


def test_split_street_hyphenated_housenumber():
    assert split_street("Kalverstraat 12-14") == ("Kalverstraat", "12-14")
