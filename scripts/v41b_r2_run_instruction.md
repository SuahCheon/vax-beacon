# v4.1b-r2 100-Case Full Run + 비교 보고서

## 목표
v4.1b-r2 (DB 전체 검토 완료 버전)의 100-case full run을 실행하고,
v4.1a baseline과 비교하여 모든 변경사항의 영향을 분석한다.

---

## Step 1: 100-Case 실행

```bash
python main.py
```

- 결과 파일명: `results/results_v41b_r2_full_100_YYYYMMDD_HHMMSS.json`
- 100개 모두 성공 확인 (ERROR 0건이어야 함)
- 실패 케이스 있으면 원인 파악 후 재실행

---

## Step 2: v4.1a vs v4.1b-r2 비교

기존 `compare_v41a_v41b.py`를 수정하거나 새 스크립트로 비교.
- v4.1a baseline: `results/results_v41a_full_100_*.json`
- v4.1b-r2: Step 1에서 생성된 파일

### 비교 항목 (전부 출력)

**A. WHO Classification 변화**
- A1/B2/C/Unclassifiable 분포 비교 (v4.1a vs v4.1b-r2)
- 개별 케이스별 WHO 변화 목록 (변한 케이스만)
- 변화 방향 집계: B2→A1, B2→C, A1→B2, C→B2 등

**B. NCI 변화 분석**
- 전체 NCI 분포 (mean, median, std)
- NCI가 변한 케이스 목록 + 변화 원인 분류:
  - weight 변경 영향 (peripheral_eosinophilia 0.7→0.5, prior_cad_history 0.7→0.5, known_autoimmune_dx 0.7→0.5)
  - Code-DB 동기화 영향 (high_degree_av_block weight 처음 적용)
  - guide 강화 영향 (plausibility 판정 변화)
  - LLM non-determinism (동일 조건에서 다른 결과)

**C. 마커별 영향 분석** (🔴 중요)
- `high_degree_av_block`: v4.1a에서 weight 미적용 → v4.1b-r2에서 적용. GCM NCI가 올라간 케이스?
- `prior_cad_history`: 0.7→0.5. ischemic NCI가 내려간 케이스?
- `peripheral_eosinophilia`: 0.7→0.5. eosinophilic NCI가 내려간 케이스?
- `known_autoimmune_dx`: 0.7→0.5. autoimmune NCI가 내려간 케이스?
- `active_covid19` (통합): sars_cov2_positive/recent_covid_infection이 있던 케이스에서 covid NCI 변화?

**D. Stage 6 품질 메트릭**
- Bridging symptom query rate (BACKGROUND_RATE/UNLIKELY 케이스)
- "vaccine vs viral" MRI framing: 0건 확인
- Investigation scope scaling: STANDARD < ENHANCED < COMPREHENSIVE 단조성
- COVID-dominant nucleocapsid recommendation rate
- Onset unknown routing 정상 작동

**E. Dominant Category 분포**
- v4.1a vs v4.1b-r2에서 dominant_alternative 분포 비교
- dominant가 변한 케이스 목록

---

## Step 3: 보고서 작성

`docs/v41b_r2_validation_report.md`로 작성. 아래 구조 따를 것.

### 보고서 구조

```
# v4.1b-r2 Validation Report

## 1. Executive Summary
- 총 변경사항 1줄 요약
- WHO 분류 변화 건수
- 핵심 결론 (개선/악화/중립)

## 2. Version Changelog (v4.1b → v4.1b-r2)
### 2.1 Phase 0: Code-DB 동기화
- NCI_WEIGHT_MATRIX: av_block_present → high_degree_av_block
- NCI_WEIGHT_MATRIX: recent_covid_infection 제거
- _identify_gaps(): COVID gap 로직 업데이트

### 2.2 Phase 1: Weight 조정
- peripheral_eosinophilia: 0.7 → 0.5 (+ guide 강화)
- prior_cad_history: 0.7 → 0.5 (+ guide 강화)
- known_autoimmune_dx: 0.7 → 0.5 (+ guide 강화)

### 2.3 Phase 2-3: Subtype 검토 + Minor Fixes
- positive_viral_pcr neg_kw 추가
- age_over_50 kw 수정
- eosinophils_on_biopsy guide 확장
- mis_a_criteria_met guide 확장
- elevated_d_dimer, concurrent_myositis neg_kw 보강

### 2.4 이전 변경 (v4.1b, 이번 run에 포함)
- active_covid19 통합 (sars_cov2_positive + recent_covid_infection 흡수)
- Stage 4/5/6 temporal investigation 체인
- MIS-C differentiation guide

## 3. WHO Classification Results
- 분포 테이블 (v4.1a vs v4.1b-r2)
- 변화 케이스 목록 (VAERS ID, 변화 방향, 원인)

## 4. NCI Impact Analysis
### 4.1 Weight 변경 영향
- 3개 마커 하향으로 인한 NCI 변화 케이스
### 4.2 Code-DB 동기화 영향
- high_degree_av_block weight 적용 효과
### 4.3 Guide 강화 영향
- plausibility 판정 변화 케이스
### 4.4 마커 통합 영향
- active_covid19 통합 효과

## 5. Stage 6 Quality Metrics
- 각 메트릭 결과 테이블

## 6. Dominant Category Distribution
- 분포 비교

## 7. Known Limitations
- LLM non-determinism 관련 건수
- 표본 크기 (n=100) 한계

## 8. Conclusion & Next Steps
```

---

## 주의사항
- `__pycache__` 정리 후 실행 (`find . -type d -name __pycache__ -exec rm -rf {} +`)
- 100개 전부 성공해야 유효한 비교임. ERROR 케이스는 재실행
- 비교 시 v4.1a baseline의 VAERS ID와 v4.1b-r2의 VAERS ID가 동일한지 확인
- NCI 변화 원인 분류 시 "LLM non-determinism"은 코드/DB 변경으로 설명 안 되는 경우에만 적용
