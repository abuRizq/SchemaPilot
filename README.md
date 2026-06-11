# SchemaPilot

A 7-layer **Single Source of Truth engine**: heterogeneous, conflicting, multilingual
tabular sources go in; one certified, fully-lineaged golden dataset comes out.

This implementation follows the two foundational specifications in this repo:

- [`THREAT_LANDSCAPE_AND_CHAOS_MAP.md`](THREAT_LANDSCAPE_AND_CHAOS_MAP.md) — *what we fight*:
  the `CHAOS-x.y.z` taxonomy of real-world data pathologies.
- [`ALGORITHMIC_ARCHITECTURE_AND_SSOT_BLUEPRINT.md`](ALGORITHMIC_ARCHITECTURE_AND_SSOT_BLUEPRINT.md) — *how we fight it*:
  the layered engine, its algorithms, and the certified-output contract.

## Quick start

```bash
pip install -e .[dev]
pytest                          # full suite incl. the CHAOS adversarial battery
python -m schemapilot.demo out/ # run the canonical 3-source collision scenario
```

The demo ingests three sources describing the same customer — an English CRM,
a US-locale billing system, and an Arabic legacy export — where *every field
conflicts* (FILE_1 §3.2), and prints the fused golden entities, their
certification tiers, and the conflict ledger. Running it twice produces
byte-identical SSOT artifacts (axiom A8).

## Layer ↔ spec ↔ module map

| Layer | Spec § | Package | What it does |
|---|---|---|---|
| L0 Ingestion & Provenance | §2 | `layer0_ingestion/` | Content-addressed immutable raw vault (re-ingestion blocked at the gate, CHAOS-1.3.9), provenance envelopes, schema-drift detection (CHAOS-1.2.3) |
| L1 Profiling & Fingerprinting | §3 | `layer1_profiling/` | One-pass column fingerprints (HLL, MinHash, Count-Min, quantile sketch, pattern/script census), chaos pre-scan → **Chaos Manifest** |
| L2 Schema Alignment | §4 | `layer2_alignment/` | Canonical Concept Ontology; deterministic matcher (nominates, never decides — A2); evidence channels E₁–E₄ with type veto (defeats homonyms, CHAOS-1.1.7); constrained global assignment; confidence gate |
| L3 Standardization | §5 | `layer3_standardize/` | A4-ordered: mojibake chain repair with round-trip proof → Unicode/Arabic match profile → temporal resolution engine (column verdicts, ambiguity intervals, sentinel excision) → locale-inferred numerics, id string-lock → typed nulls |
| L4 Entity Resolution | §6 | `layer4_resolution/` | Multi-pass blocking incl. cross-script phonetic bridge (CHAOS-3.1.2); comparison vectors; Fellegi–Sunter EM; agglomerative clustering with cannot-link + chimera veto (no transitive closure — A5/A6) |
| L5 Fusion | §7 | `layer5_fusion/` | Conflict typing & entropy; strategy arsenal (multiplicity, recency, specificity, completeness, Bayesian truth discovery); golden records with ERASED and no-fabrication bars *enforced as exceptions* |
| L6 Certification | §9–10 | `layer6_certification/` | Dual-grain constraints (row + population: Benford, default-mass, fan-out reconciliation); monotone trust composition; the five-part SSOT artifact |
| Complexity Router | §8 | `router.py` | FAST/STANDARD/DEEP per column from the Chaos Manifest; one-way evidence-triggered escalation |
| Adjudication | A7 | `adjudication.py` | Human queue ranked by uncertainty × impact; answers accrete into the CCO |
| Orchestration | §1 | `pipeline.py` | L0→L6 with both feedback loops (chimera veto, reliability priors); pinned-seed determinism |

## The SSOT artifact (five parts, §9.2)

`pipeline.run()` writes to `<out>/ssot/`:

1. `golden_entities.parquet` — one row per (entity, attribute) with value, trust, tier, strategy, sources for/against, entropy
2. `identity_crosswalk.parquet` — bitemporal source-record ↔ entity map
3. `conflict_ledger.parquet` — every losing value, queryable forever
4. `lineage_graph.json` — cell-level transform chains back to vault bytes
5. `trust_certificate.json` — tier census, reconciliation arithmetic, open escalations

Plus `reliability_priors.json` — the R[source, domain] matrix fed back into the next run.

## The threat map is the test plan (§10.5)

`tests/chaos/` is the permanent adversarial regression suite; every test cites
the `CHAOS-x.y.z` class it defends against, so coverage is grep-able:

```bash
grep -rn "CHAOS-" tests/ | grep -oE "CHAOS-[0-9.]+" | sort -u
```

All seven top-tier risks from FILE_1 §6 (3.2.7 chimera, 2.1.1 date ambiguity,
4.1.1 fan-out, 1.1.7 homonyms, 3.3.3 ID collision, 2.2.x encoding, 2.1.8
timezone loss) have dedicated passing tests, alongside the end-to-end battery
in `tests/test_end_to_end.py` asserting the canonical scenario's ground truth:
one Mohammed Al-Rashid entity, majority DOB with the contest escalated to
humans, both phones kept, recency-correct address, the GDPR-erased phone never
refilled, and byte-identical reruns.

## Documented approximations

Exotic components ship as faithful, swappable approximations behind stable interfaces:

- **E₁ label embeddings** (`LabelEmbedder`): character-trigram cosine + the CCO's
  multilingual label edges; a sentence-transformer implements the same two methods.
- **Beider–Morse phonetics** (`consonant_skeleton`): language-aware romanization
  to consonant skeletons (`Mohammed`/`Muhammad`/`محمد` → `mhmd`), with و/ي
  treated as long-vowel carriers.
- **t-digest** (`QuantileSketch`): deterministic stride-doubling decimation sketch.
- **Hijri calendar**: tabular (arithmetic) conversion, ±1 day vs observational.
