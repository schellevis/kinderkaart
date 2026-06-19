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


def test_combined_split_merge_ids_distinct():
    reg = Registry.load("/nonexistent.json")
    reg.assign(_mk([["rce-musea/a", "osm/b"], ["wikidata-museums/c"]]))
    ids = reg.assign(_mk([["rce-musea/a"], ["osm/b", "wikidata-museums/c"]]))
    assert ids[0] != ids[1]  # C1: no duplicate id across clusters


def test_ambiguous_split_tombstones_old_id():
    reg = Registry.load("/nonexistent.json")
    reg.assign(_mk([["wikidata-museums/Q1", "osm/b"]]))  # one id, 2 members
    ids = reg.assign(_mk([["wikidata-museums/Q1"], ["osm/b"]]))  # each overlaps by 1 -> tie
    assert reg.is_tombstone("wikidata-museums/Q1")  # I1: old id tombstoned
    assert ids[0] != "wikidata-museums/Q1"
    assert ids[1] != "wikidata-museums/Q1"


def test_merge_then_split_no_stale_alias():
    reg = Registry.load("/nonexistent.json")
    reg.assign(_mk([["rce-musea/m1"], ["wikidata-museums/Q1"]]))  # two ids
    reg.assign(_mk([["rce-musea/m1", "wikidata-museums/Q1"]]))  # merge
    assert "wikidata-museums/Q1" in reg.aliases_for("rce-musea/m1")
    reg.assign(_mk([["rce-musea/m1"], ["wikidata-museums/Q1"]]))  # split back
    # I2: no active id may appear in any other entry's aliases.
    active = {p for p, e in reg.entries.items() if e["status"] == "active"}
    for e in reg.entries.values():
        for a in e["aliases"]:
            assert a not in active


def test_assign_returns_distinct_ids_invariant():
    reg = Registry.load("/nonexistent.json")
    reg.assign(
        _mk(
            [
                ["rce-musea/m1"],
                ["wikidata-museums/Q1"],
                ["osm/node/9"],  # will be deleted next build
            ]
        )
    )
    # next build: m1+Q1 merge, node/9 deleted, fresh cluster appears
    ids = reg.assign(
        _mk(
            [
                ["rce-musea/m1", "wikidata-museums/Q1"],  # merge
                ["osm/node/42"],  # new
            ]
        )
    )
    assert reg.is_tombstone("osm/node/9")  # deletion
    assert len(set(ids.values())) == len(ids)


def test_registry_file_idempotent_with_delete_and_merge(tmp_path):
    p1 = tmp_path / "id1.json"
    p2 = tmp_path / "id2.json"
    reg = Registry.load(str(p1))
    reg.assign(
        _mk([["rce-musea/m1"], ["wikidata-museums/Q1"], ["osm/node/9"]])
    )
    build2 = _mk([["rce-musea/m1", "wikidata-museums/Q1"], ["osm/node/42"]])
    reg.assign(build2)
    reg.save(str(p1))
    first = p1.read_text()

    reg2 = Registry.load(str(p1))
    reg2.assign(build2)  # same clusters re-assigned
    reg2.save(str(p2))
    assert p2.read_text() == first  # byte-identical
