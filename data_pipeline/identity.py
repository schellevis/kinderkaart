from __future__ import annotations

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
        m2id = self._member_to_id()
        # For each cluster, find the set of prior ids its members map to.
        cluster_ids: list[set[str]] = []
        for members in clusters:
            cluster_ids.append({m2id[m] for m in members if m in m2id})

        # Detect splits: a prior id referenced by >1 cluster.
        # Pre-compute split resolutions: for each split id, which cluster wins?
        id_to_clusters: dict[str, list[int]] = {}
        for idx, ids in enumerate(cluster_ids):
            for pid in ids:
                id_to_clusters.setdefault(pid, []).append(idx)

        # split_winner[pid] = winning cluster idx, or None if tie (tombstone all)
        split_winner: dict[str, int | None] = {}
        for pid, cluster_idxs in id_to_clusters.items():
            if len(cluster_idxs) <= 1:
                continue
            prior_members = set(self.entries[pid]["members"])
            # (overlap_count, -cluster_idx) for stable sort: larger overlap wins,
            # tie-break by smaller cluster index (deterministic)
            overlaps = sorted(
                ((len(prior_members & set(clusters[i])), -i, i) for i in cluster_idxs),
                reverse=True,
            )
            top, second = overlaps[0], overlaps[1]
            if top[0] == second[0]:
                # Ambiguous tie -> tombstone, all mint new
                self.entries[pid]["status"] = "tombstone"
                self.entries[pid]["members"] = []
                split_winner[pid] = None
            else:
                split_winner[pid] = top[2]

        result: dict[int, str] = {}
        seen_input_members: set[str] = set()
        # Process clusters in deterministic order (by sorted first member).
        order = sorted(range(len(clusters)), key=lambda i: clusters[i][0])
        for idx in order:
            members = clusters[idx]
            seen_input_members.update(members)
            prior = sorted(cluster_ids[idx], key=_id_rank)

            if not prior:  # mint
                pid = _mint_id(members)
            elif len(prior) == 1:
                pid = prior[0]
                if pid in split_winner:  # split scenario
                    winner_idx = split_winner[pid]
                    if winner_idx is None or winner_idx != idx:
                        # This cluster is not the winner (or tie) -> mint new id
                        pid = _mint_id(members)
                    # else: this cluster is the winner -> keep pid
            else:  # merge
                survivor = prior[0]
                for loser in prior[1:]:
                    self.entries[survivor]["aliases"] = sorted(
                        set(self.entries[survivor]["aliases"]) | {loser}
                        | set(self.entries[loser]["aliases"])
                    )
                    self.entries[loser]["status"] = "tombstone"
                    self.entries[loser]["members"] = []
                pid = survivor

            self.entries.setdefault(pid, {"members": [], "aliases": [], "status": "active"})
            self.entries[pid]["status"] = "active"
            self.entries[pid]["members"] = sorted(set(members))
            result[idx] = pid

        # Deletion: previously-active ids with no members in this input -> tombstone.
        for pid, e in self.entries.items():
            if e["status"] == "active" and pid not in result.values():
                if not any(m in seen_input_members for m in e["members"]):
                    e["status"] = "tombstone"
                    e["members"] = []
        return result

    def aliases_for(self, poi_id: str) -> list[str]:
        return self.entries.get(poi_id, {}).get("aliases", [])

    def is_tombstone(self, poi_id: str) -> bool:
        return self.entries.get(poi_id, {}).get("status") == "tombstone"

    def save(self, path: str | Path) -> None:
        payload = {"entries": self.entries}
        Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
