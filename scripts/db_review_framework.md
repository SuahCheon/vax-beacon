# ddx_myocarditis.json — DB 전체 검토 프레임워크 (v2)

> Updated after `sars_cov2_positive` 제거 + `recent_covid_infection` 흡수 완료

## 1. DB 설계 원칙

### 1.1 DB의 역할
- **Stage 3B (Code)**: `extraction_keywords`로 DDx candidate 매칭, `negative_keywords`로 false positive 차단
- **Stage 3C (LLM)**: `differentiation_guide`를 참조하여 plausibility 판정 (none/low/moderate/high)
- **Stage 3D (Code)**: `weight`로 NCI 점수 계산 → `classify()`의 입력값 결정

**DB가 곧 임상 판단 기준선** — keyword에 없으면 매칭 안 되고, guide에 없으면 LLM이 잘못 판단하고, weight가 틀리면 분류가 바뀜.

### 1.2 Weight 설계 원칙
| Tier | Weight 범위 | 의미 | classify() 영향 |
|------|-----------|------|----------------|
| Confirmatory | 0.9-1.0 | 조직검사 등 확진 소견 | 단독으로 C (≥0.7) |
| High | 0.6-0.8 | 병인 특이적 핵심 소견 | 단독으로 C 가능 (≥0.7) 또는 B2 (≥0.4) |
| Medium | 0.3-0.5 | 감별 보조 소견 | 단독으로 B2 가능 (≥0.4), 조합 시 C |
| Low | 0.1-0.2 | 비특이적 지지 소견 | 단독 영향 없음, 조합 시 B2 가능 |
| Zero | 0.0 | 위험인자 (audit trail용) | NCI 기여 없음 |

**핵심 원칙**: weight는 "이 소견이 존재할 때, 대안 병인(백신 외)의 가능성이 얼마나 높아지는가"를 반영. 백신 심근염에서도 흔히 나타나는 소견은 낮은 weight. Stage 3C의 plausibility 판정이 최종 NCI에 반영되므로, weight는 "만약 이 마커가 진짜라면"의 최대 NCI 기여도를 의미.

### 1.3 Marker 카테고리 구조
- **primary_indicators**: 해당 subtype을 직접 시사하는 소견
- **supporting_indicators**: 단독으로는 약하지만 primary와 함께 의미 있는 소견
- **confirmatory**: 확진 검사 (biopsy, catheterization 등)

### 1.4 Keyword 설계 원칙
- **extraction_keywords**: VAERS narrative에 나타날 수 있는 임상 용어 (sensitivity 우선)
- **negative_keywords**: false positive 차단 부정 표현 (최소 3개 권장)
- **differentiation_guide**: Stage 3C LLM의 plausibility 판단 기준. "이 소견이 백신 심근염 vs 대안 병인 중 어느 쪽을 더 시사하는가"에 초점. 시간적 개연성, 임상 맥락 등 판단 조건을 명시.

### 1.5 마커 통합 원칙 (v4.1b에서 확립)
같은 임상 현상의 다른 서술 방식이 다른 NCI 결과를 낳으면 안 된다. 동일한 임상적 의미를 가진 마커는 하나로 통합하되, `differentiation_guide`에서 세분화된 판단 기준(시간적 개연성, 중증도 등)을 제공하여 Stage 3C LLM이 plausibility를 차등 판정하도록 한다.

---

## 2. 현재 상태 (v4.1b, 34 markers)

### 해결된 이슈
- ~~🔴 Issue 1: `active_covid19` ↔ `sars_cov2_positive` 키워드 중복~~ → `sars_cov2_positive` 제거, `active_covid19`에 흡수
- ~~🟡 Issue 2: `viral_etiology.positive_viral_pcr` ↔ `covid19_related.sars_cov2_positive` 키워드 중복~~ → 마커 제거로 해결
- ~~`recent_covid_infection` 서술 방식에 따른 NCI 변동~~ → `active_covid19`에 흡수, guide에 시간적 개연성 기반 판단 통합

### 남은 이슈
| # | 심각도 | 내용 | 영향 |
|---|--------|------|------|
| 3 | 🟡 | `concurrent_myositis` neg_kw 2개 | false positive 리스크 낮음 (ICI 맥락 필요) |
| 4 | 🟢 | `elevated_d_dimer` neg_kw 2개 | false positive 리스크 낮음 (low weight 0.2) |
| 5 | ⬜ | NCI 집계 로직 (max vs sum) 미확인 | Stage 3D 코드 확인 필요 |

### Cross-subtype keyword overlap: **0건** ✅
### Intra-subtype keyword overlap: **0건** ✅

---

## 3. Subtype별 검토 체크리스트

### A. 마커 커버리지
- [ ] 해당 병인의 주요 임상 소견이 모두 포함되어 있는가?
- [ ] 누락된 감별 소견은 없는가?
- [ ] VAERS narrative에서 흔히 나타나는 표현이 keywords에 포함되어 있는가?

### B. Weight 적정성
- [ ] 단독 C trigger (≥0.7) 마커가 정말 확진급 소견인가?
- [ ] 단독 B2 trigger (≥0.4) 마커가 정말 감별 필요 소견인가?
- [ ] 백신 심근염에서도 흔한 소견이 높은 weight를 받고 있지 않은가?

### C. Differentiation Guide 품질
- [ ] "백신 심근염 vs 이 대안 병인"의 감별 포인트가 명확한가?
- [ ] 시간적 개연성, 중증도 등 판단 조건이 구체적으로 명시되어 있는가?
- [ ] LLM이 오해할 수 있는 모호한 표현이 없는가?

### D. Keyword/Negative 품질
- [ ] extraction_keywords ≥ 5개 (충분한 sensitivity)
- [ ] negative_keywords ≥ 3개 (권장)
- [ ] 다른 subtype/마커와 keyword 중복 없음

### E. 임상 정확성
- [ ] pathophysiology 설명이 현재 의학 지식과 일치하는가?
- [ ] high_suspicion_criteria가 실제 임상 기준과 부합하는가?

---

## 4. Subtype별 현재 구조 + 검토 상태

### 4.1 viral_etiology (6 markers) — ⬜ 미검토

| Cat | Finding | Weight | kw | neg | guide |
|-----|---------|--------|-----|-----|-------|
| PRI | positive_viral_pcr | 0.80 | 15 | 7 | 221ch |
| PRI | lymphocytosis | 0.15 | 5 | 4 | 220ch |
| SUP | fever_reported | 0.20 | 12 | 3 | 275ch |
| SUP | uri_symptoms | 0.20 | 11 | 3 | 172ch |
| SUP | gi_symptoms | 0.20 | 8 | 4 | 210ch |
| SUP | myalgia_arthralgia | 0.15 | 6 | 4 | 294ch |

**검토 포인트:**
- `positive_viral_pcr` (w=0.8): 단독 C trigger. COVID 결과는 neg_kw에 "covid"로 차단 중 — 충분한가?
- supporting markers (fever, URI, GI, myalgia)는 모두 **백신 reactogenicity**와 겹칠 수 있음 — guide에서 구분이 명확한가?
- 누락 가능: specific viral serology (paired titers), viral cardiotropism markers

### 4.2 giant_cell_myocarditis (5 markers) — ✅ 검토 완료 (v4.1a-patch1)

| Cat | Finding | Weight | kw | neg | guide |
|-----|---------|--------|-----|-----|-------|
| PRI | rapid_heart_failure | 0.60 | 13 | 5 | 444ch |
| PRI | high_degree_av_block | 0.50 | 10 | 13 | 619ch |
| PRI | ventricular_arrhythmia | 0.50 | 14 | 7 | 327ch |
| PRI | cardiogenic_shock | 0.40 | 15 | 3 | 219ch |
| CONF | giant_cells_on_biopsy | 1.00 | 6 | 4 | 174ch |

**Status:** patch1에서 `high_degree_av_block` severity 분리, negative_keywords 13개로 강화. 검증 완료.

### 4.3 eosinophilic_myocarditis (4 markers) — ⬜ 미검토

| Cat | Finding | Weight | kw | neg | guide |
|-----|---------|--------|-----|-----|-------|
| PRI | peripheral_eosinophilia | 0.70 | 6 | 3 | 225ch |
| PRI | new_medication_history | 0.30 | 12 | 3 | 246ch |
| SUP | hypersensitivity_rash | 0.20 | 11 | 3 | 204ch |
| CONF | eosinophils_on_biopsy | 1.00 | 5 | 3 | 114ch |

**검토 포인트:**
- `peripheral_eosinophilia` (w=0.7): 단독 C trigger — 적절한가? 호산구 증가 자체가 확진급인가?
- `new_medication_history` kw에 vaccine 자체가 포함되지 않도록 확인 필요
- 누락 가능: parasitic infection markers (travel history, eosinophilia + parasite)

### 4.4 toxin_ici_myocarditis (5 markers) — ✅ 검토 완료 (v4.1a-patch1)

| Cat | Finding | Weight | kw | neg | guide |
|-----|---------|--------|-----|-----|-------|
| PRI | ici_therapy_active | 0.80 | 15 | 3 | 277ch |
| PRI | concurrent_myositis | 0.50 | 6 | **2** | 199ch |
| PRI | conduction_delay | 0.40 | 10 | 8 | 988ch |
| SUP | new_chemotherapy | 0.40 | 12 | 3 | 261ch |
| SUP | elevated_ck | 0.30 | 6 | 3 | 247ch |

**Status:** patch1에서 `conduction_delay` TWO MANDATORY requirements 강화. `concurrent_myositis` neg_kw 2개 — 보강 권장.

### 4.5 ischemic_heart_disease (6 markers) — ⬜ 미검토

| Cat | Finding | Weight | kw | neg | guide |
|-----|---------|--------|-----|-----|-------|
| PRI | prior_cad_history | 0.70 | 13 | 5 | 271ch |
| PRI | focal_st_changes | 0.50 | 10 | 8 | 525ch |
| SUP | age_over_50 | 0.00 | 16 | 4 | 219ch |
| SUP | diabetes_hypertension | 0.00 | 9 | 3 | 196ch |
| SUP | smoking_history | 0.00 | 6 | 3 | 80ch |
| CONF | positive_catheterization | 1.00 | 18 | 7 | 800ch |

**검토 포인트:**
- `prior_cad_history` (w=0.7): 단독 C trigger — CAD 이력만으로 현재 심근염의 대안 원인으로 볼 수 있는가? 기존 CAD 환자도 백신 심근염 발생 가능
- `positive_catheterization`에 SCAD가 포함됨 — SCAD는 CAD와 별개 pathophysiology. 별도 마커 또는 별도 subtype 필요?
- `age_over_50` kw: "age 5"가 "age 50-59"를 잡으려는 것이나, "age 5" (5세)도 매칭될 위험

### 4.6 covid19_related (4 markers) — 🟡 부분 검토

| Cat | Finding | Weight | kw | neg | guide |
|-----|---------|--------|-----|-----|-------|
| PRI | active_covid19 | 0.80 | 23 | 12 | 1326ch |
| PRI | mis_c_criteria_met | 0.60 | 5 | 3 | 689ch |
| PRI | mis_a_criteria_met | 0.60 | 4 | 3 | 215ch |
| SUP | elevated_d_dimer | 0.20 | 5 | **2** | 227ch |

**Status:** `active_covid19` 통합 완료 (sars_cov2_positive + recent_covid_infection 흡수). 시간적 개연성 guide 구현. `elevated_d_dimer` neg_kw 2개 — 보강 권장.

### 4.7 autoimmune_inflammatory (4 markers) — ⬜ 미검토

| Cat | Finding | Weight | kw | neg | guide |
|-----|---------|--------|-----|-----|-------|
| PRI | known_autoimmune_dx | 0.70 | 22 | 3 | 322ch |
| PRI | positive_ana_dsdna | 0.50 | 10 | 4 | 285ch |
| SUP | systemic_inflammation | 0.30 | 11 | 4 | 362ch |
| CONF | granulomas_on_biopsy | 0.90 | 6 | 3 | 193ch |

**검토 포인트:**
- `known_autoimmune_dx` (w=0.7): 단독 C trigger — 자가면역 질환 이력만으로 현재 심근염의 대안 원인이 되는가? 자가면역 환자도 백신 심근염 발생 가능
- `systemic_inflammation`: CRP/ESR 상승은 백신 심근염에서도 흔함 — guide에서 수준 구분이 있는가?
- 누락 가능: cardiac sarcoidosis markers (별도 subtype?)

---

## 5. 단독 C Trigger (w ≥ 0.7) 임상 적정성 검토

이 마커들은 Stage 3C에서 plausibility=high를 받으면 **단독으로 NCI ≥ 0.7 → classify()에서 C**가 될 수 있다.

| Subtype | Marker | Weight | 단독 C 적절? | 비고 |
|---------|--------|--------|-------------|------|
| viral | positive_viral_pcr | 0.8 | ✅ | 확인된 바이러스 감염 = 강력한 대안 원인 |
| eosinophilic | peripheral_eosinophilia | 0.7 | ⚠️ 검토 | 호산구 증가만으로 확진급? 약제 유발 가능 |
| toxin_ici | ici_therapy_active | 0.8 | ✅ | ICI 치료 중 심근염 = 강력한 대안 원인 |
| ischemic | prior_cad_history | 0.7 | ⚠️ 검토 | CAD 이력만으로는 현재 event 원인 불확실 |
| covid19 | active_covid19 | 0.8 | ✅ | 하지만 guide의 plausibility로 걸러짐 |
| autoimmune | known_autoimmune_dx | 0.7 | ⚠️ 검토 | 자가면역 이력만으로는 현재 event 원인 불확실 |

**⚠️ 3개 마커는 v4.1b 100-case 결과에서 실제 C 분류에 기여하는지 확인 필요**

---

## 6. 검토 우선순위

1. **Stage 3D NCI 집계 로직 확인** — max vs sum 여부가 모든 weight 적정성 판단의 전제
2. **단독 C trigger 3개** (`peripheral_eosinophilia`, `prior_cad_history`, `known_autoimmune_dx`) weight 적정성
3. **viral_etiology** — reactogenicity 구분, 누락 마커
4. **ischemic_heart_disease** — `age_over_50` kw 문제, SCAD 처리
5. **eosinophilic / autoimmune** — 드문 케이스, 100-case 결과 기반
6. **minor fixes** — neg_kw 부족 2건 (`concurrent_myositis`, `elevated_d_dimer`)

---

## 7. 후속 작업

- [ ] Stage 3D NCI 집계 로직 확인 (코드 리뷰)
- [ ] v4.1b 100-case 결과에서 subtype별 매칭 빈도 + NCI 기여 분석
- [ ] 단독 C trigger weight 적정성 확정
- [ ] 미검토 subtype 순차 검토 (viral → ischemic → eosinophilic → autoimmune)
- [ ] minor neg_kw 보강
- [ ] 완성된 설계 원칙을 `knowledge/README.md`로 문서화
