from data_pipeline.textnorm import name_similarity, normalize_name, website_host


def test_normalize_strips_accents_articles_punct():
    assert normalize_name("De Café-Réstaurant 't Hoekje!") == "cafe restaurant hoekje"
    assert normalize_name("Het Spoorwegmuseum") == "spoorwegmuseum"


def test_similarity_high_for_same_place():
    assert name_similarity("Rijksmuseum", "het rijksmuseum") > 0.9


def test_similarity_low_for_different():
    assert name_similarity("Speeltuin Noord", "Museum Volkenkunde") < 0.5


def test_website_host_normalizes():
    assert website_host("https://WWW.Rijksmuseum.nl/en/visit") == "rijksmuseum.nl"
    assert website_host(None) is None
