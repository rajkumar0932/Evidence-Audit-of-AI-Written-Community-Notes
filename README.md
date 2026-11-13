# Do AI Fact-Checks Say What Their Sources Say?

*Working title.* This is an independent audit of the evidence behind AI-written Community Notes on X. It asks whether the sources a note cites actually support what the note claims, and whether the platform's Helpful ratings track that support.

Everything in this repository was written during the Apart Research **AI x Epistemics Research Sprint** (13–16 Nov 2026). No code or data predates the sprint.

## Status

- [x] Public data snapshot pinned (`data/raw/2026-11-12/SHA256SUMS`; the raw files are not re-hosted)
- [x] Sampling frame and stratified sample (`scripts/01_build_frame.py`, `scripts/02_sample.py`)
- [x] Pre-registration, stage 1 (`PREREGISTRATION.md`)
- [ ] Source retrieval pinned to note time · claim decomposition · quote-anchored verdicts
- [ ] Blind human validation · ratings linkage · analysis · evidence rejector

## Reproduce

```bash
uv sync
# Download the 2026-11-12 dump files listed in data/raw/2026-11-12/SHA256SUMS into that folder, then:
uv run python scripts/01_build_frame.py     # sampling frame (~3 min)
uv run python scripts/02_sample.py          # stratified sample (seeded)
uv run python scripts/03_stream_ratings.py  # rater tags for frame notes, streamed (~10 min)
```

## Data

The data comes from X's public Community Notes download. Participant IDs are pseudonymous. This repository releases only note IDs, derived labels and code. To recover note text, rebuild from the public dump.
