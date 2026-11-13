"""Draw the pre-registered stratified sample and the disjoint pilot sample.

Design (main window, notes with >= 1 URL, collaborative notes and notes without a status row excluded):
  3 groups (cw, ai_other, human) x 3 statuses:
    CRH  (Currently Rated Helpful)     110 per group  -- the notes users actually see
    CRNH (Currently Rated Not Helpful)  78 per group  -- cw has exactly 78, so it is a census for cw
    NMR  (Needs More Ratings)           80 per group
  => 804 notes. Pilot: 40 notes from 1-9 Nov (prompt development only, never analysed).

Outputs
  data/interim/sample_main.parquet, data/interim/sample_pilot.parquet   (full rows, local only)
  data/release/sample_ids.csv     noteId + stratum (committed with the pre-registration)
  data/release/strata_sizes.csv   population size of every cell, for weighting

Run:  uv run python scripts/02_sample.py
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from common import GROUPS, INTERIM, RELEASE, SEED, STATUS_SHORT, fmt_ms

CELL_N = {"CURRENTLY_RATED_HELPFUL": 110, "CURRENTLY_RATED_NOT_HELPFUL": 78, "NEEDS_MORE_RATINGS": 80}
N_PILOT_PER_GROUP = {"cw": 14, "ai_other": 13, "human": 13}


def draw(pop: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    pop = pop.sort_values("noteId")  # deterministic order before sampling
    if len(pop) <= n:
        return pop
    rng = np.random.default_rng(seed)
    return pop.iloc[np.sort(rng.choice(len(pop), size=n, replace=False))]


def main() -> None:
    f = pd.read_parquet(INTERIM / "frame.parquet")
    eligible = f[f.group.isin(GROUPS) & (f.n_urls >= 1) & (f.status != "MISSING")]

    parts, sizes = [], []
    for gi, g in enumerate(GROUPS):
        for si, (status, n) in enumerate(CELL_N.items()):
            pop = eligible[(eligible.window == "main") & (eligible.group == g) & (eligible.status == status)]
            s = draw(pop, n, SEED + 10 * gi + si).assign(stratum=f"{g}|{STATUS_SHORT[status]}", split="main")
            parts.append(s)
            sizes.append({"stratum": f"{g}|{STATUS_SHORT[status]}", "group": g, "status": STATUS_SHORT[status],
                          "population": len(pop), "sampled": len(s), "weight": len(pop) / max(len(s), 1)})
    main = pd.concat(parts, ignore_index=True)

    pilot_parts = []
    for gi, g in enumerate(GROUPS):
        pop = eligible[(eligible.window == "pilot") & (eligible.group == g)]
        pilot_parts.append(draw(pop, N_PILOT_PER_GROUP[g], SEED + 1000 + gi)
                           .assign(stratum=lambda d: d.group + "|" + d.status.map(STATUS_SHORT), split="pilot"))
    pilot = pd.concat(pilot_parts, ignore_index=True)

    assert not set(main.noteId) & set(pilot.noteId)
    main.to_parquet(INTERIM / "sample_main.parquet", index=False)
    pilot.to_parquet(INTERIM / "sample_pilot.parquet", index=False)

    ids = pd.concat([main, pilot])[["noteId", "split", "stratum", "group", "status", "created_ms", "n_urls"]]
    ids["created_utc"] = ids.pop("created_ms").map(fmt_ms)
    ids.to_csv(RELEASE / "sample_ids.csv", index=False)
    pd.DataFrame(sizes).to_csv(RELEASE / "strata_sizes.csv", index=False)

    print(pd.DataFrame(sizes).to_string(index=False, float_format=lambda x: f"{x:.1f}"))
    print(f"\nmain sample: {len(main)} notes, {int(main.n_urls.sum())} URLs "
          f"(web {int(main.n_web.sum())}, wiki {int(main.n_wiki.sum())}, nontext {int(main.n_nontext.sum())}, "
          f"x_post {int(main.n_x_post.sum())}, x_other {int(main.n_x_other.sum())})")
    print(f"pilot sample: {len(pilot)} notes ({pilot.stratum.value_counts().to_dict()})")
    digest = hashlib.sha256((RELEASE / "sample_ids.csv").read_bytes()).hexdigest()
    print(f"\nsha256(data/release/sample_ids.csv) = {digest}")


if __name__ == "__main__":
    main()
