from data_pipeline.identity import Registry


def _mk(members_per_cluster):
    return [sorted(c) for c in members_per_cluster]


def test_mint_uses_highest_priority_member():
    reg = Registry.load("/nonexistent.json")  # empty
    ids = reg.assign(_mk([["wikidata-museums/Q1", "osm/node/9"]]))
    # rce/wikidata/osm priority -> wikidata-museums outranks osm
    assert ids[0] == "wikidata-museums/Q1"


def test_match_reuses_id_across_builds():
    reg = Registry.load("/nonexistent.json")
    reg.assign(_mk([["rce-musea/m1", "wikidata-museums/Q1"]]))
    # next build: same place, osm record now also present
    ids = reg.assign(_mk([["rce-musea/m1", "wikidata-museums/Q1", "osm/node/3"]]))
    assert ids[0] == "rce-musea/m1"  # stable survivor id


def test_merge_records_aliases():
    reg = Registry.load("/nonexistent.json")
    reg.assign(_mk([["rce-musea/m1"], ["wikidata-museums/Q1"]]))  # two ids minted
    ids = reg.assign(_mk([["rce-musea/m1", "wikidata-museums/Q1"]]))  # now merged
    survivor = ids[0]
    assert survivor == "rce-musea/m1"  # higher rank
    assert "wikidata-museums/Q1" in reg.aliases_for(survivor)


def test_split_largest_overlap_keeps_id():
    reg = Registry.load("/nonexistent.json")
    reg.assign(_mk([["rce-musea/m1", "osm/node/3", "osm/node/4"]]))
    ids = reg.assign(_mk([["rce-musea/m1", "osm/node/3"], ["osm/node/4"]]))
    assert ids[0] == "rce-musea/m1"   # larger overlap keeps id
    assert ids[1] != "rce-musea/m1"   # minted new


def test_deletion_tombstones(tmp_path):
    reg = Registry.load(str(tmp_path / "id.json"))
    reg.assign(_mk([["osm/node/1"]]))
    reg.assign(_mk([["osm/node/2"]]))  # node/1 gone
    assert reg.is_tombstone("osm/node/1")


def test_save_is_deterministic(tmp_path):
    p = tmp_path / "id.json"
    reg = Registry.load(str(p))
    reg.assign(_mk([["rce-musea/m1", "wikidata-museums/Q1"]]))
    reg.save(str(p))
    first = p.read_text()
    reg2 = Registry.load(str(p))
    reg2.assign(_mk([["rce-musea/m1", "wikidata-museums/Q1"]]))
    reg2.save(str(p))
    assert p.read_text() == first  # idempotent
