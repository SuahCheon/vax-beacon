# ddx_myocarditis.json — DB 전체 검토 실행계획

**목적:** DB의 임상적 정확성, 구조적 일관성, 코드-DB 동기화 검증
**전제:** v4.1b 코드 변경 완료, NCI 집계 방식 확인 완료
**산출물:** 수정된 DB (version bump) + 동기화된 Stage 3D 코드 + knowledge/README.md

---

## NCI 집계 방식 (확인 완료)

- **Subtype 내**: 마커별 weight **합산**, 1.0 cap
- **Subtype 간**: **max** 취함 → `max_nci`가 classify()의 입력
- **Plausibility gate**: present=True + is_acute_concordant=True + plausibility ∈ {high, moderate}

**시사점:**
- 같은 subtype 내 마커 2개가 동시에 pass하면 합산됨 (예: `rapid_heart_failure`(0.6) + `ventricular_arrhythmia`(0.5) = 1.0 → capped 1.0)
- 단독 C trigger (w≥0.7)는 plausibility=high일 때만 실제 C를 유발
- plausibility=moderate인 0.7 마커는 NCI=0.7 → C threshold에 정확히 걸림

---

## Phase 0: Code-DB 동기화 (🔴 CRITICAL — 반드시 먼저)

### 발견된 불일치

| 위치 | 문제 | 영향 |
|------|------|------|
| `NCI_WEIGHT_MATRIX` | `av_block_present` (구 이름) | DB에는 `high_degree_av_block`으로 변경됨. Stage 3C가 DB 기반으로 `high_degree_av_block` 출력 → Stage 3D에서 weight 매칭 실패 → NCI=0 (weight 적용 안 됨) |
| `NCI_WEIGHT_MATRIX` | `recent_covid_infection` (삭제된 마커) | DB에서 제거됨 → Stage 3C 출력에 없음 → dead code |
| `_identify_gaps()` | `recent_covid_infection` 참조 | 삭제된 마커를 참조 → gap 로직 작동 안 함 |
| `NCI_WEIGHT_MATRIX` | `sars_cov2_positive` 없음 | 이미 제거했으므로 OK (코드에 추가된 적 없음) |

### 수정 내용

**File: `pipeline/stage3d_nci_calculator.py`**

1. `NCI_WEIGHT_MATRIX["giant_cell_myocarditis"]`: `"av_block_present": 0.5` → `"high_degree_av_block": 0.5`
2. `NCI_WEIGHT_MATRIX["covid19_related"]`: `"recent_covid_infection": 0.4` 제거
3. `_identify_gaps()`: `recent_covid_infection` 참조를 `active_covid19` 기반으로 업데이트

### 검증

```bash
python main.py --case 1413266   # GCM marker 매칭 확인 (incomplete RBBB → 매칭 안 됨 유지)
python main.py --case 1343980   # COVID dominant case → NCI 확인
```

- [ ] `high_degree_av_block` weight가 Stage 3D에서 올바르게 적용되는지 확인
- [ ] `recent_covid_infection` 제거로 인한 에러 없음
- [ ] `_identify_gaps()` COVID gap 로직 정상 작동

---

## Phase 1: 단독 C Trigger Weight 적정성 (~30min)

w ≥ 0.7 마커 중 plausibility=high → 단독 NCI ≥ 0.7 → C 분류 가능.
"이력/상태"만으로 C가 되는 것이 적절한지 검토.

### 검토 대상

| Marker | Weight | 현재 판단 | 검토 필요 사유 |
|--------|--------|----------|--------------|
| `positive_viral_pcr` | 0.8 | ✅ 적절 | 확인된 바이러스 = 강력한 대안 원인 |
| `ici_therapy_active` | 0.8 | ✅ 적절 | ICI 치료 중 심근염 = 강력한 대안 원인 |
| `active_covid19` | 0.8 | ✅ 적절 | guide의 temporal plausibility로 gate됨 |
| `peripheral_eosinophilia` | 0.7 | ⚠️ | 호산구증가 단독 = 확진급? 약제/기생충 감별 안 됨 |
| `prior_cad_history` | 0.7 | ⚠️ | CAD 이력 ≠ 현재 event 원인. CAD 환자도 백신 심근염 가능 |
| `known_autoimmune_dx` | 0.7 | ⚠️ | 자가면역 이력 ≠ 현재 flare. 안정기 환자도 백신 심근염 가능 |

### 판단 기준
- "이 소견이 present + plausibility=high이면, 현재 심근염이 백신이 아닌 이 원인일 가능성이 70% 이상인가?"
- 이력/상태 마커는 **현재 활성** 여부가 guide에서 구분되어야 함

### 가능한 조치
- weight 하향 (0.7 → 0.5 등) — B2는 유발하되 단독 C는 안 되도록
- guide 강화 — "이력만으로는 plausibility=moderate 이하" 명시
- 현행 유지 — guide에서 이미 걸러진다면

---

## Phase 2: Subtype별 순차 검토 (~2h)

프레임워크 체크리스트(A~E) 적용. 우선순위 순서대로.

### 2-1. viral_etiology (6 markers)

**검토 포인트:**
- [ ] `positive_viral_pcr` neg_kw에 "covid" 있음 — "SARS", "coronavirus"도 추가 필요?
- [ ] supporting markers (fever, URI, GI, myalgia)의 guide: 백신 reactogenicity vs viral prodrome 구분 충분한가?
- [ ] 누락 마커: paired serology (acute/convalescent titers)?
- [ ] `fever_reported` kw "chills" — 백신 반응에서도 흔함. guide에서 구분?

### 2-2. ischemic_heart_disease (6 markers)

**검토 포인트:**
- [ ] `prior_cad_history` weight 적정성 (Phase 1 결과 반영)
- [ ] `age_over_50` kw: "age 5"가 5세도 매칭 위험 → kw 수정 필요
- [ ] `positive_catheterization`에 SCAD 포함 — 별도 처리 필요?
- [ ] `focal_st_changes` kw "ST elevation" — 심근염에서도 ST elevation 흔함. guide에서 "territorial" 구분 충분?

### 2-3. eosinophilic_myocarditis (4 markers)

**검토 포인트:**
- [ ] `peripheral_eosinophilia` weight 적정성 (Phase 1 결과 반영)
- [ ] `new_medication_history`: vaccine 자체가 매칭되지 않도록 확인
- [ ] 누락 마커: parasitic infection? hypereosinophilic syndrome?
- [ ] `eosinophils_on_biopsy` guide가 114ch로 가장 짧음 — 보강 필요?

### 2-4. autoimmune_inflammatory (4 markers)

**검토 포인트:**
- [ ] `known_autoimmune_dx` weight 적정성 (Phase 1 결과 반영)
- [ ] kw 22개로 넓음 — false positive 리스크? (예: "thyroid" → 하시모토 갑상선염이 심근염과 무관할 수 있음)
- [ ] `systemic_inflammation` (CRP/ESR): 백신 심근염에서도 상승 — guide 구분 수준?
- [ ] cardiac sarcoidosis: 현재 `granulomas_on_biopsy`로 커버되나, 별도 subtype 필요?

### 2-5. covid19_related (4 markers) — 부분 완료

**검토 포인트:**
- [ ] `active_covid19` guide의 시간적 개연성 4단계가 Stage 3C LLM에게 충분히 명확한가?
- [ ] `mis_a_criteria_met` guide가 215ch로 간략 — `mis_c_criteria_met`(689ch) 수준으로 보강?
- [ ] `elevated_d_dimer` neg_kw 2개 → 3개로 보강

### 2-6. giant_cell / toxin_ici — 검토 완료, minor만

**Minor:**
- [ ] `concurrent_myositis` neg_kw 2개 → 3개로 보강 ("normal CK" 추가)

---

## Phase 3: Minor Fixes 일괄 적용 (~15min)

Phase 1~2에서 결정된 수정사항 반영:
- neg_kw 보강 (최소 3개)
- kw 수정 (`age_over_50` 등)
- guide 보강
- weight 조정 (필요시)

---

## Phase 4: NCI_WEIGHT_MATRIX 동기화 확인 (~10min)

Phase 3까지의 DB 수정 후, `stage3d_nci_calculator.py`의 `NCI_WEIGHT_MATRIX`가 DB와 완전히 일치하는지 자동 검증 스크립트 실행.

```python
# verify_db_code_sync.py
# DB의 모든 marker finding name + weight와
# NCI_WEIGHT_MATRIX의 모든 marker name + weight를 비교
# 불일치 시 에러 출력
```

---

## Phase 5: 문서화 (~20min)

### `knowledge/README.md` 작성
- DB 설계 원칙 (프레임워크 Section 1)
- 각 subtype의 임상 근거 요약
- weight tier 설명
- 변경 이력 (v4.0 → v4.1a-patch1 → v4.1b → 현재)

### DB version bump
- `ddx_myocarditis.json` version → 다음 버전 (v4.1b 유지 또는 v4.1b-r2)
- `investigation_protocols.json` version 동기화

---

## Phase 6: 검증 — 단일 케이스 (~20min)

Phase 0~3 수정 후, 기존 검증 케이스 재실행:

```bash
python main.py --case 1413266   # GCM/conduction marker (patch1 검증)
python main.py --case 1286607   # Day 0, A1 standard
python main.py --case 1343980   # COVID dominant
python main.py --case 1501224   # GCM dominant
```

- [ ] 모든 케이스 에러 없이 실행
- [ ] WHO 분류가 기대값과 일치
- [ ] Stage 3D NCI 계산에서 marker name 매칭 정상

---

## 수정 대상 파일 요약

| File | Phase | Change |
|------|-------|--------|
| `pipeline/stage3d_nci_calculator.py` | 0 | NCI_WEIGHT_MATRIX 동기화 + _identify_gaps() 수정 |
| `knowledge/ddx_myocarditis.json` | 1-3 | weight/guide/kw/neg 수정 |
| `knowledge/investigation_protocols.json` | 2 | 필요시 동기화 |
| `knowledge/README.md` | 5 | NEW — 설계 문서 |
| `verify_db_code_sync.py` | 4 | NEW — 동기화 검증 스크립트 |

## Estimated Time: ~4h (Phase 0-1 의사결정 포함)
