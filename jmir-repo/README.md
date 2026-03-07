# Vax-Beacon (JMIR Publication Version)

**AI-Generated Investigation Guidance for Vaccine Adverse Event Surveillance**

A neuro-symbolic AI pipeline that processes passive surveillance reports of suspected vaccine adverse events and generates structured investigation guidance for field epidemiologists.

## Live Demo

**[Interactive Case Report Viewer](https://suahcheon.github.io/vax-beacon-jmir/)**

4 representative VAERS myocarditis/pericarditis cases demonstrating distinct pipeline pathways:
- **Brighton L4** &rarr; Early exit with targeted investigation guidance
- **WHO A1** &rarr; Vaccine-associated with monitoring recommendations
- **WHO B2** &rarr; Indeterminate with targeted viral testing guidance
- **WHO C** &rarr; Coincidental with escalation for giant cell myocarditis

## Architecture

6-agent, 9-stage neuro-symbolic pipeline:
- **Neural perception**: LLM extracts clinical observations (Claude Sonnet 4)
- **Symbolic reasoning**: Deterministic code executes all classification decisions
- **Investigation guidance**: Structured recommendations via Claude Haiku 4.5

Every classification is reproducible. Every reasoning step is traceable to published evidence.

## Key Design Principle: Designed Deference

When data is too incomplete for assessment (20% of cases), the system doesn't guess &mdash; it defers. It generates targeted investigation guidance specifying what tests to order, in what priority, and what certainty level each unlocks.

## Paper

Submitted to **JMIR Public Health and Surveillance** (2026).

> Cheon ME, Son EC. AI-Generated Investigation Guidance for Vaccine Adverse Event Surveillance: Development and Evaluation of a Neuro-Symbolic Causality Assessment Pipeline.

## Related

- **Pipeline code (MedGemma 4B edge deployment version)**: [github.com/SuahCheon/vax-beacon](https://github.com/SuahCheon/vax-beacon)
- **Validation dataset**: [Kaggle](https://www.kaggle.com/datasets/myeongeuncheon/hexavax-maps-100-case-validation-cohort)

## License

MIT
