# Vax-Beacon: Scalable AEFI Causality Assessment Using Quantized MedGemma 4B

AI-Powered WHO AEFI Causality Assessment — a 6-agent hybrid reasoning pipeline that deploys MedGemma 4B (4-bit quantized, 3.2 GB VRAM) on consumer-grade hardware for reproducible vaccine safety surveillance.

---

## Quick Start

```bash
pip install -r requirements.txt
set HF_TOKEN=hf_your_token_here          # Windows (Linux/Mac: export HF_TOKEN=...)
python main.py --backend medgemma         # Run full 100-case benchmark
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

## Benchmark Results

### WHO Category Distribution (N=100)

| WHO Category | Claude 3.5 Sonnet | MedGemma 4B |
|:---|:---|:---|
| A1 (Consistent) | 41 (41%) | 21 (21%) |
| B2 (Indeterminate) | 5 (5%) | 9 (9%) |
| C (Coincidental) | 27 (27%) | 21 (21%) |
| Unclassifiable | 25 (25%) | 47 (48%) |
| Error / Timeout | 2 (2%) | 2 (2%) |

| Metric | Result |
|--------|--------|
| **Showcase Accuracy** (4 expert-validated cases) | **4/4 (100%)** |
| **Pipeline Completion Rate** | **98/100 (98%)** |
| **Baseline Concordance** (Claude vs MedGemma) | **54.1%** |
| **Decision Reproducibility** | **100%** (deterministic code path) |
| **Guidance Generation Rate** | **98/98 (100%)** |

100% of the concordance gap stems from **input extraction quality**, not reasoning capability. The deterministic decision logic is identical across both backends — improving the extraction layer (via MedGemma 27B or domain-finetuned models) would directly close this gap without any architectural changes.

---

## The 24% Finding

24 of 100 cases triggered Brighton L4 early exit — insufficient diagnostic evidence for any causality assessment. Each received targeted, prioritized investigation recommendations. This transforms data gaps into actionable investigation leads for field officers, demonstrating the system's primary surveillance value beyond classification.

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

*Vax-Beacon | MedGemma 4B (4-bit quantized, 3.2 GB VRAM) | N=100 VAERS Benchmark | RTX 4050 Consumer GPU*
