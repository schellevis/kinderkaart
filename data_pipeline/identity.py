from __future__ import annotations

import hashlib
import json
from pathlib import Path

from data_pipeline.merge_config import source_rank


def _member_rank(member_key: str) -> tuple[int, str]:
    source_id = member_key.split("/", 1)[0]
    return (source_rank(source_id)[0], member_key)


def _mint_id(members: list[str]) -> str:
    return min(members, key=_member_rank)


def _id_rank(poi_id: str) -> tuple[int, str]:
    source_id = poi_id.split("/", 1)[0]
    return (source_rank(source_id)[0], poi_id)


class Registry:
    def __init__(self, data: dict | None = None) -> None:
        data = data or {}
        # poi_id -> {"members": [..], "aliases": [..], "status": "active"|"tombstone"}
        self.entries: dict[str, dict] = data.get("entries", {})

    @classmethod
    def load(cls, path: str | Path) -> "Registry":
        p = Path(path)
        if not p.exists():
            return cls()
        return cls(json.loads(p.read_text()))

    def _member_to_id(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pid, e in self.entries.items():
            if e["status"] == "active":
                for m in e["members"]:
                    out[m] = pid
        return out

    def assign(self, clusters: list[list[str]]) -> dict[int, str]:
        # Step 1: active member-key -> poi_id, and prior members per active id.
        m2id: dict[str, str] = {}
        prior_members: dict[str, set[str]] = {}
        for pid, e in self.entries.items():
            if e["status"] == "active":
                prior_members[pid] = set(e["members"])
                for m in e["members"]:
                    m2id[m] = pid

        # Step 2: prior ids referenced by each cluster.
        cluster_member_sets: list[set[str]] = [set(c) for c in clusters]
        cluster_refs: list[set[str]] = [
            {m2id[m] for m in members if m in m2id} for members in clusters
        ]
        referenced: set[str] = set()
        for refs in cluster_refs:
            referenced |= refs

        # Step 3: for each referenced prior id, which cluster (if any) may claim it.
        # claimable[pid] = cluster index, or None if ambiguous tie.
        claimable: dict[str, int | None] = {}
        for pid in sorted(referenced, key=_id_rank):
            pmembers = prior_members[pid]
            overlaps = [
                (len(pmembers & cluster_member_sets[i]), i)
                for i in range(len(clusters))
            ]
            maxov = max(ov for ov, _ in overlaps)
            top = sorted(
                (i for ov, i in overlaps if ov == maxov),
                key=lambda i: clusters[i][0],
            )
            if len(top) == 1:
                claimable[pid] = top[0]
            else:
                claimable[pid] = None  # ambiguous

        # Step 4: group claims per cluster.
        cluster_claims: dict[int, list[str]] = {}
        for pid, ci in claimable.items():
            if ci is not None:
                cluster_claims.setdefault(ci, []).append(pid)

        # Step 5: per cluster, pick the kept id (highest _id_rank claim) and
        # identify merge losers.
        kept_id: dict[int, str] = {}
        merge_losers: set[str] = set()
        loser_to_survivor: dict[str, str] = {}
        order = sorted(range(len(clusters)), key=lambda i: clusters[i][0])
        for idx in order:
            claims = cluster_claims.get(idx)
            if not claims:
                continue
            claims_sorted = sorted(claims, key=_id_rank)
            keep = claims_sorted[0]
            kept_id[idx] = keep
            for loser in claims_sorted[1:]:
                merge_losers.add(loser)
                loser_to_survivor[loser] = keep

        # Step 6: tombstone set computed BEFORE minting.
        ambiguous = {pid for pid, ci in claimable.items() if ci is None}
        deletions = {pid for pid in prior_members if pid not in referenced}
        tombstoned: set[str] = ambiguous | merge_losers | deletions

        # Step 7: mint ids for clusters with no kept id.
        used_ids: set[str] = set(kept_id.values())
        minted_id: dict[int, str] = {}
        for idx in order:
            if idx in kept_id:
                continue
            members = clusters[idx]
            base = min(members, key=_member_rank)
            if base not in used_ids and base not in tombstoned:
                pid = base
            else:
                digest = hashlib.sha1("|".join(sorted(members)).encode()).hexdigest()[:8]
                pid = f"{base}#{digest}"
            minted_id[idx] = pid
            used_ids.add(pid)

        # Step 8: apply state deterministically.
        result: dict[int, str] = {}

        # Helper: reactivate an id (kept or minted) and strip it from any alias list.
        def _activate(pid: str, members: list[str]) -> None:
            self.entries.setdefault(
                pid, {"members": [], "aliases": [], "status": "active"}
            )
            self.entries[pid]["status"] = "active"
            self.entries[pid]["members"] = sorted(set(members))
            # I2 fix: an active id must not remain an alias of any other entry.
            for other, e in self.entries.items():
                if other == pid:
                    continue
                if pid in e["aliases"]:
                    e["aliases"] = [a for a in e["aliases"] if a != pid]

        for idx in order:
            if idx in kept_id:
                pid = kept_id[idx]
                _activate(pid, clusters[idx])
            else:
                pid = minted_id[idx]
                _activate(pid, clusters[idx])
                self.entries[pid]["aliases"] = []
            result[idx] = pid

        # Merge losers: tombstone and fold into survivor's aliases (transitively).
        for loser in sorted(merge_losers, key=_id_rank):
            survivor = loser_to_survivor[loser]
            transitive = {loser} | set(self.entries[loser].get("aliases", []))
            self.entries[survivor]["aliases"] = sorted(
                set(self.entries[survivor]["aliases"]) | transitive
            )
            self.entries[loser]["status"] = "tombstone"
            self.entries[loser]["members"] = []

        # Ambiguous + deletion pids: tombstone with no alias added.
        for pid in (ambiguous | deletions):
            self.entries[pid]["status"] = "tombstone"
            self.entries[pid]["members"] = []

        # Step 9: invariants.
        values = list(result.values())
        assert len(set(values)) == len(values), "duplicate poi_id assigned"
        active_ids = {p for p, e in self.entries.items() if e["status"] == "active"}
        for p, e in self.entries.items():
            for a in e["aliases"]:
                assert a not in active_ids, f"active id {a} appears as alias of {p}"
        return result

    def aliases_for(self, poi_id: str) -> list[str]:
        return self.entries.get(poi_id, {}).get("aliases", [])

    def is_tombstone(self, poi_id: str) -> bool:
        return self.entries.get(poi_id, {}).get("status") == "tombstone"

    def save(self, path: str | Path) -> None:
        payload = {"entries": self.entries}
        Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
