"""Topic identity across runs: new / matched / potential split / potential merge / uncertain (pure).

Matching stays the existing one-to-one greedy centroid assignment (`match_topics`). On top of it, pairs that
fall short of the match threshold are never silently dropped or silently merged: they are classified so a
split or merge is reported as such instead of looking like an ordinary match or an unrelated new topic.

Outcomes (each new topic gets exactly one):
  matched          one-to-one match above the threshold; keeps the stored topic id and its history
  potential_split  no match of its own, but similar (>= floor) to a stored topic that another new topic
                   claimed -> this topic may be a part that broke off; it gets a NEW id
  potential_merge  matched, but a second stored topic that no new topic claimed is also similar (>= floor)
                   to it -> it may have absorbed that topic; keeps the matched id, the other is listed
  uncertain        similar (>= floor, < threshold) to an unclaimed stored topic: identity unclear; NEW id
  new              nothing similar enough in the stored topics; NEW id

A potential split/merge is a similarity-geometry signal, not proof; the decision records the similarities.
"""
from dataclasses import dataclass, field

import numpy as np

from app.intelligence.topic_representations import match_topics

NEW, MATCHED, SPLIT, MERGE, UNCERTAIN = "new", "matched", "potential_split", "potential_merge", "uncertain"
OUTCOMES = (NEW, MATCHED, SPLIT, MERGE, UNCERTAIN)


@dataclass
class IdentityDecision:
    outcome: str
    matched_topic_id: str | None = None  # the stored id this topic inherits (matched / potential_merge only)
    similarity: float | None = None  # similarity to matched_topic_id, or to the best related stored topic
    related_topic_ids: list[str] = field(default_factory=list)  # split parent / merged-in / uncertain candidate
    related_similarities: list[float] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "matched_topic_id": self.matched_topic_id,
            "similarity": None if self.similarity is None else round(self.similarity, 4),
            "related_topic_ids": self.related_topic_ids,
            "related_similarities": [round(x, 4) for x in self.related_similarities],
        }


def _unit(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    return m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-9, None)


def resolve_identities(
    new: dict[int, np.ndarray], prior: dict[str, np.ndarray], threshold: float, floor: float
) -> dict[int, IdentityDecision]:
    floor = min(floor, threshold)
    if not new:
        return {}
    if not prior:
        return {k: IdentityDecision(NEW) for k in new}

    nkeys, pkeys = list(new), list(prior)
    sims = _unit(np.vstack([new[k] for k in nkeys])) @ _unit(np.vstack([prior[k] for k in pkeys])).T
    pidx = {k: j for j, k in enumerate(pkeys)}

    matches = match_topics(new, prior, threshold)  # {new_key: (prior_key, sim)}
    claimed = {pid for pid, _ in matches.values()}
    out: dict[int, IdentityDecision] = {}

    for i, nk in enumerate(nkeys):
        if nk in matches:
            pid, sim = matches[nk]
            # unclaimed stored topics that are also close to this one: it may have merged them
            others = [(float(sims[i, j]), pk) for pk, j in pidx.items() if pk != pid and pk not in claimed and sims[i, j] >= floor]
            others.sort(reverse=True)
            if others:
                out[nk] = IdentityDecision(MERGE, pid, sim, [pk for _, pk in others], [s for s, _ in others])
            else:
                out[nk] = IdentityDecision(MATCHED, pid, sim)
            continue

        near = [(float(sims[i, j]), pk) for pk, j in pidx.items() if sims[i, j] >= floor]
        near.sort(reverse=True)
        if not near:
            out[nk] = IdentityDecision(NEW)
            continue
        best_sim, best_pid = near[0]
        if best_pid in claimed:
            out[nk] = IdentityDecision(SPLIT, None, best_sim, [pk for _, pk in near if pk in claimed], [s for s, pk in near if pk in claimed])
        else:
            out[nk] = IdentityDecision(UNCERTAIN, None, best_sim, [pk for _, pk in near], [s for s, _ in near])
    return out
