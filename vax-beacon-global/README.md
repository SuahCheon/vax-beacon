# vax-beacon-global — PoC 1 & 2: Hybrid Reasoning + Field Validation

> *In development. See open Issues for roadmap.*

This module extends the local MedGemma engine (vax-beacon-engine) toward a **Global Secure Hybrid (GSH)** architecture — combining local data sovereignty with cloud-level reasoning quality, validated against clinical expert judgment and field epidemiologist utility.

---

## PoC 1: Clinical Fidelity Validation

**Question:** Can a hybrid pipeline (local extraction → cloud reasoning) achieve cardiologist-level NCI scoring?

**Approach:**
- Replace MedGemma Stage 3 observation with Claude Sonnet API
- Cardiologist review of NCI scores for 20–50 representative cases
- Metric: Inter-rater agreement (Cohen's κ) on WHO category assignment

**Key component:** `ddx_myocarditis.json` — non-causal index weights co-developed with cardiology specialist (Euncheol Son, MD PhD, University of Ulsan College of Medicine)

---

## PoC 2: Operational Utility Study (HITL)

**Question:** Does Stage 6 investigation guidance reduce field epidemiologist workload and improve investigation quality?

**Approach:**
- Structured survey with field epidemiologists
- Metrics: guidance specificity, investigation planning time reduction, user trust score
- Target: 30% reduction in investigation planning time (primary endpoint)

---

## GSH Security Protocol

```
LOCAL ENVIRONMENT          CLOUD API
─────────────────          ─────────
Raw VAERS narrative    →   [Anonymization] → Clinical markers only
Patient identifiers    ✗   Never transmitted
Brighton level         →   Passed as structured input
NCI score              →   Computed locally, sent for reasoning validation
```

PII (patient names, dates of birth, addresses) never leave the local environment. Only structured clinical markers and anonymized case metadata are transmitted to cloud APIs.

---

## Status

- [ ] PoC 1 architecture design
- [ ] Anonymization token specification
- [ ] Cardiology expert review protocol
- [ ] PoC 2 survey instrument design
- [ ] IRB / ethics review (if required)

See [open Issues](https://github.com/SuahCheon/vax-beacon/issues) for detailed task tracking.
