# vax-beacon-engine — PoC 0: Local SLM Baseline

> MedGemma 4B (4-bit quantized, 3.2 GB VRAM) on consumer hardware

This is the production-ready local pipeline — PoC 0 of the Vax-Beacon architecture. It demonstrates that WHO AEFI causality assessment can run on consumer-grade GPUs (RTX 4050 equivalent) with zero cloud dependency and complete data sovereignty.

---

## Quick Start

```bash
pip install -r requirements.txt
export HF_TOKEN=hf_your_token_here       # Windows: set HF_TOKEN=...
python main.py --backend medgemma        # MedGemma 4B (requires GPU)
python main.py --backend anthropic       # Claude Sonnet 4 (requires API key)
python main.py --backend anthropic --limit 5  # Quick test, 5 cases
```

---

## Benchmark Results (N=100, 0 errors)

| WHO Category | Claude Sonnet 4 | MedGemma 4B |
|---|---|---|
| A1 (Vaccine-associated) | 45% | 25% |
| C (Coincidental) | 27% | 31% |
| Unclassifiable | 21% | 22% |
| B2 (Indeterminate) | 7% | 22% |
| Pipeline errors | **0%** | **0%** |

**MedGemma baseline concordance with Claude: 62%** — gap attributable entirely to clinical observation quality, not classification logic (which is identical and deterministic).

**Runtime:** ~48 min for 100 cases (Claude Sonnet 4 backend)
**VRAM:** ~3.2 GB (MedGemma 4B, 4-bit quantized)

---

## The 19–21% Brighton L4 Finding

Cases with insufficient diagnostic evidence trigger early exit at Stage 2 (Brighton Level 4). These cases receive targeted investigation recommendations from Stage 6 rather than a forced classification. This demonstrates the system's primary value: **transforming data gaps into actionable investigation leads** for field epidemiologists.

---

## Technical Specification

| Component | Spec |
|---|---|
| Python | 3.10+ |
| GPU | NVIDIA RTX 4050 or equivalent (6+ GB VRAM) |
| VRAM | ~3.2 GB (4-bit quantized MedGemma 4B) |
| LLM calls | Temperature 0.1 globally |
| Claude model | claude-sonnet-4-20250514 (Stage 6) |

---

## Architecture Notes

- `config.py`: All constants, model settings, temporal windows (NAM 2024)
- `pipeline/`: One file per stage (stage1–stage6)
- `knowledge/ddx_myocarditis.json`: Authoritative DDx marker source (Altman et al. 2023)
- `main.py`: Orchestration + benchmark runner
- `--resume` flag: Restart interrupted batch runs from last checkpoint

See root [README.md](../README.md) for full architecture overview.
