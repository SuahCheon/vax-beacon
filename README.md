# Vax-Beacon: Multi-Agent AEFI Causality Pipeline

> *AI constrained. Epidemiologist augmented.*

A neuro-symbolic AI pipeline for WHO AEFI causality assessment of vaccine adverse event reports. Vax-Beacon operationalizes the WHO 2019 causality assessment framework through a 6-agent, 9-stage architecture where **LLMs observe, deterministic code decides**.

Developed by a field epidemiologist who experienced the 2021 COVID-19 vaccination campaign firsthand — when overwhelming AEFI volume met a structural gap in timely specialist guidance.

---

## The Problem

Post-authorization vaccine safety surveillance depends on field epidemiologists who must:
- Assess AEFI causality in real time, often before specialist panels convene
- Apply complex WHO classification logic to incomplete passive surveillance data
- Produce investigation guidance for signals that may not yet have published protocols

The result: inconsistent assessment quality, delayed investigation initiation, and irretrievable acute-phase data.

---

## The Architecture

### Core Design Principle: AI Observes, Code Decides

```
┌─────────────────────────────────────────────────────────┐
│  ORACLE TRAP: Delegating classification to LLMs         │
│  in safety-critical pipelines is a failure mode.        │
│  LLMs observe. Deterministic code decides.              │
│              — Designed Deference                       │
└─────────────────────────────────────────────────────────┘
```

| Stage | Role | Decision Maker |
|-------|------|----------------|
| 1 — ICSR Extractor | Narrative → structured fields | LLM (observation) + Code (parsing) |
| 2 — Brighton Validator | Diagnostic certainty level | **Code only** |
| 3A–3D — DDx Specialist | Alternative cause markers + NCI | LLM (markers) + **Code** (NCI score) |
| 4 — Auditor | Temporal plausibility | **Code only** (NAM 2024 windows) |
| 5 — Causality Assessor | WHO A1/B2/C classification | **Code only** (decision tree) |
| 6 — Guidance Advisor | Investigation recommendations | **Code** (templates) + LLM (narrative) |

### Global Secure Hybrid (GSH) Roadmap

```
PoC 0 (vax-beacon-engine/)   → Local SLM (MedGemma 4B, 3.2 GB VRAM)
PoC 1 (vax-beacon-global/)   → Cloud API (Claude) + NCI clinical validation
PoC 2 (vax-beacon-global/)   → Field epidemiologist HITL utility study
```

Data sovereignty guarantee: PII never leaves local environment. Only anonymized clinical markers pass to cloud APIs in hybrid deployment.

---

## Repository Structure

```
vax-beacon/
├── vax-beacon-engine/   # PoC 0 — MedGemma 4B local pipeline (production-ready)
├── vax-beacon-global/   # PoC 1 & 2 — Hybrid reasoning + field validation (in development)
└── docs/                # Architecture diagrams, cohort curation guide, schema
```

---

## Key Results (N=100 VAERS benchmark, Claude Sonnet 4 backend)

| WHO Category | N | % |
|---|---|---|
| A1 — Vaccine-associated | 45 | 45% |
| C — Coincidental | 27 | 27% |
| Unclassifiable | 21 | 21% |
| B2 — Indeterminate | 7 | 7% |
| Pipeline errors | **0** | **0%** |

21% unclassifiable = Brighton L4 early exit (insufficient diagnostic evidence) → each case receives targeted investigation recommendations. **This is a feature, not a limitation.**

---

## Status

- **PoC 0:** Complete. 100-case benchmark, 0 errors, ~48 min runtime.
- **Manuscript:** Under preparation for *JMIR Public Health and Surveillance*.
- **Interactive pipeline viewer:** [suahcheon.github.io/vax-beacon-jmir](https://suahcheon.github.io/vax-beacon-jmir/)
- **PoC 1 & 2:** Planned. See [vax-beacon-global/README.md](./vax-beacon-global/README.md) and open Issues.

---

## Citation

```bibtex
@software{vax_beacon_2026,
  author    = {Cheon, Myeong-eun},
  title     = {Vax-Beacon: Multi-Agent AEFI Causality Pipeline},
  year      = {2026},
  url       = {https://github.com/SuahCheon/vax-beacon},
  note      = {Korea Disease Control and Prevention Agency}
}
```

---

*MIT License | Developed at KDCA | WHO AEFI 2019 framework*
