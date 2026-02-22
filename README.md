# Vax-Beacon: Scalable AEFI Causality Assessment Using Quantized MedGemma 4B

AI-Powered WHO AEFI Causality Assessment — a 6-agent hybrid reasoning pipeline that deploys MedGemma 4B (4-bit quantized, 3.2 GB VRAM) on consumer-grade hardware for reproducible vaccine safety surveillance.

---

## Quick Start

```bash
pip install -r requirements.txt
set HF_TOKEN=hf_your_token_here          # Windows (Linux/Mac: export HF_TOKEN=...)
python main.py --backend medgemma         # Run full 100-case benchmark
python main.py --backend anthropic        # Run with Claude Sonnet 4 (requires API key)
```

---

## Architecture

6-agent, 9-stage pipeline where each component operates within its competency boundary:

| Stage | Agent | Intelligence Type | MedGemma Role |
|-------|-------|-------------------|---------------|
| 1 | ICSR Extractor | Neural + Symbolic | Short narrative summary only; structured fields parsed by code |
| 2 | Brighton Validator | Symbolic | None — rule-based diagnostic certainty classification |
| 3A-3D | DDx Specialist | Neural + Symbolic | Clinical marker observation (≤10-word rationales); NCI scoring by code |
| 4 | Auditor | Symbolic | None — known AE registry + NAM 2024 temporal windows |
| 5 | Causality Assessor | Symbolic + Neural | WHO classification by deterministic decision tree; reasoning summary by MedGemma |
| 6 | Guidance Advisor | Symbolic | None — code templates + JSON knowledge database |

---

## Key Design: Observe vs. Compute

MedGemma is restricted to **clinical observation** — extracting markers, summarizing narratives, generating short rationales. All **classification decisions** are made by deterministic code: Brighton levels, NCI scoring, WHO category assignment. Every MedGemma call has a code-only fallback; if the model fails at any stage, the pipeline continues with deterministic output. Classification accuracy is architecturally guaranteed to never degrade below the code-only baseline.

---

## Robustness Engineering

Three layers of fault tolerance ensure unattended batch execution completes without human intervention:

| Layer | Mechanism | Detail |
|-------|-----------|--------|
| **Internal StoppingCriteria** | `_TimeLimitCriteria` (120s) + `_StopOnJsonClose` | Halts `model.generate()` from inside the CUDA kernel — no zombie threads, no external thread timeouts |
| **JSON Retry with Repair** | 3-attempt loop with structural repair | Strips invalid escapes, removes comments, fixes trailing commas, converts single quotes; each retry appends a JSON-enforcement hint |
| **Stage-level Graceful Degradation** | Per-stage `try/except` with fallback output | If any LLM stage fails, the pipeline substitutes a deterministic fallback (e.g., empty observations for Stage 3A, code-only classification for Stage 5) and continues to the next stage |
| **Keyword-Augmented Extraction** | Regex-based clinical data extraction | Numeric value extraction (troponin levels, LVEF%, CRP/BNP values) supplements LLM extraction, preventing Brighton L4 misclassification from truncated narratives |

Additional safeguards: streaming CSV (flush per case for crash recovery), incremental JSON checkpoints every 25 cases, `--resume` flag to skip already-completed cases, VRAM monitoring with automatic `torch.cuda.empty_cache()` after each case, and stdout broken-pipe guard for long batch runs.

---

## Benchmark Results (v4)

### WHO Category Distribution (N=100)

| WHO Category | Claude Sonnet 4 | MedGemma 4B |
|:---|:---|:---|
| A1 (Vaccine-associated) | 46 (46%) | 25 (25%) |
| B2 (Indeterminate) | 6 (6%) | 22 (22%) |
| C (Coincidental) | 27 (27%) | 31 (31%) |
| Unclassifiable | 21 (21%) | 22 (22%) |
| Error / Timeout | **0 (0%)** | **0 (0%)** |

### Key Metrics

| Metric | Claude Sonnet 4 | MedGemma 4B |
|--------|----------------|-------------|
| **Pipeline Completion Rate** | 100/100 (100%) | 100/100 (100%) |
| **Baseline Concordance** | — | **62%** (62/100) |
| **Showcase Accuracy** (4 expert-validated cases) | 4/4 (100%) | 4/4 (100%) |
| **Decision Reproducibility** | 100% | 100% |
| **Guidance Generation Rate** | 100/100 (100%) | 100/100 (100%) |

### Understanding the 62% Concordance

The dominant disagreement pattern — Claude A1 → MedGemma B2 (16 cases, 42% of all disagreements) — reveals an asymmetry between observation and reasoning in 4B models. MedGemma successfully detects clinically relevant alternative markers (viral symptoms, cardiac dysfunction indicators, ischemic risk factors) but lacks the contextual reasoning capacity to evaluate whether those markers are clinically significant for the acute event. For example, a pre-existing risk factor is correctly identified but over-weighted as a plausible acute cause, inflating the NCI score and shifting the classification from A1 to B2.

The deterministic decision logic is identical across both backends. 100% of the concordance gap stems from **clinical observation quality and contextual reasoning**, not from the classification engine itself. Improving the observation layer (via MedGemma 27B or domain-finetuned models) would directly close this gap without any architectural changes.

MedGemma's B2 bias represents a pragmatically conservative stance: flagging borderline cases for human review rather than premature causal attribution — a safer failure mode in pharmacovigilance.

---

## The 19% Finding

19 of 100 cases triggered Brighton L4 early exit — insufficient diagnostic evidence for any causality assessment. Each received targeted, prioritized investigation recommendations. This transforms data gaps into actionable investigation leads for field officers, demonstrating the system's primary surveillance value beyond classification.

---

## Requirements

| Component | Specification |
|-----------|--------------|
| Python | 3.10+ |
| GPU | NVIDIA RTX 4050 or equivalent (6+ GB VRAM) |
| VRAM Usage | ~3.2 GB (4-bit quantized MedGemma 4B) |
| HuggingFace | Access token with MedGemma model agreement |

---

## License

MIT

---

## Repository

[github.com/SuahCheon/vax-beacon](https://github.com/SuahCheon/vax-beacon)

---

## References

[1] National Academies of Sciences, Engineering, and Medicine. *Evidence Review of the Adverse Effects of COVID-19 Vaccination and Intramuscular Vaccine Administration.* Washington, DC: The National Academies Press; 2024. DOI: 10.17226/27746. PMID: 39312602.

[2] World Health Organization. *Causality Assessment of an Adverse Event Following Immunization (AEFI): User Manual for the Revised WHO Classification, Second Edition, 2019 Update.* Geneva: WHO; 2019. ISBN: 978-92-4-151699-0.

[3] Altman NL, Berning AA, Mann SC, Quaife RA, Gill EA, Auerbach SR, Campbell TB, Bristow MR. Vaccination-Associated Myocarditis and Myocardial Injury. Circ Res. 2023;132(10):1338-1357. DOI: 10.1161/CIRCRESAHA.122.321881. PMID: 37167355.

[4] Sexson Tejtel SK, Munoz FM, Al-Ammouri I, et al. Myocarditis and pericarditis: Case definition and guidelines for data collection, analysis, and presentation of immunization safety data. *Vaccine.* 2022;40(10):1499-1511. DOI: [10.1016/j.vaccine.2021.11.074](https://doi.org/10.1016/j.vaccine.2021.11.074). PMID: 35105494.

---

*Vax-Beacon | MedGemma 4B (4-bit quantized, 3.2 GB VRAM) | N=100 VAERS Benchmark | RTX 4050 Consumer GPU*
