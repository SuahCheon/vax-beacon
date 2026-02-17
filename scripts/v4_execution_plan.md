# Vax-Beacon v4 실행계획

**작성일:** 2025-02-15
**업데이트:** 2025-02-15 (v3.1 결과 반영, 설계 결정 확정)
**작업일:** 2025-02-16 (일)
**목표:** v4 아키텍처 리팩토링 → 전체 100건 재실행 → v3.0/v3.1/v4 삼자 비교

---

## Phase 0: v3.1 100건 결과 분석 ✅ 완료

### 확정된 결과

**분류 분포 (v3.0 → v3.1):**

| Category | v3.0 | v3.1 | Delta |
|---|---|---|---|
| A1 | 21 | 30 | +9 |
| B1 | 9 | 9 | 0 |
| B2 | 29 | 16 | -13 |
| C | 17 | 21 | +4 |
| Unclassifiable | 1 | 1 | 0 |

**전환 패턴 (15건):**
- B2→A1: 10건 — nuance 분리 핵심 효과
- B2→C: 4건 — NCI drift(마커 비결정성)로 NCI 상승
- A1→B2: 1건 — 역방향 drift (1482907: rapid_heart_failure F→T)

**Guard override: 2건**

| VAERS | LLM 출력 | Guard 보정 | 사유 |
|---|---|---|---|
| 983362 | B2 | A1 | KnownAE + temporal + NCI=0.35 < 0.4 |
| 1793549 | B2 | A1 | KnownAE + temporal + NCI=0.3 < 0.4 |

**NCI Drift (|delta| >= 0.15): 5건 — v4의 핵심 근거**

| VAERS | v3.0 NCI | v3.1 NCI | delta | WHO 변경 | 마커 flip |
|---|---|---|---|---|---|
| 1482907 | 0.00 | 0.60 | +0.60 | A1→B2 | rapid_heart_failure: F→T |
| 1347846 | 0.60 | 0.95 | +0.35 | B2→C | positive_viral_pcr: F→T |
| 977955 | 0.00 | 0.30 | +0.30 | B1→B1 | systemic_inflammation: F→T |
| 983362 | 0.50 | 0.35 | -0.15 | B2→A1 | focal_st_changes: T→F |
| 1128543 | 0.50 | 0.35 | -0.15 | C→C | lymphocytosis: T→F |

→ 5건 모두 마커 flip 동반. LLM이 동일 narrative에서 다른 판단. v4 two-pass로 해결 목표.

**Stage 6 구체성:**
- GCM-dominant → EMB: 22/22 (100%) ✅
- Viral-dominant → viral panel: 20/21 (95%) ✅
- Viral-dominant → Lake Louise: 15/21 (71%) — DB 참조로 100% 목표

**1313197 (v3.1 full run):** NCI=0.5, epistemic_uncertainty=0.6, WHO=B2, EMB=CRITICAL ✅

### 결과 파일 위치

```
results/
  results_v30_initial.json   ← 복사본 (원본: results_full_100_20260215_153510.json)
  results_v30_final.json     ← 복사본 (원본: results_full_100_20260215_170319.json)
  results_v31.json           ← 복사본 (원본: results_full_100_20260215_195721.json)
```

### 확정된 설계 결정
- **DB 형태:** JSON 파일 (규모 적합, Git 친화, Kaggle 이식 용이)
- **Stage 3:** two-pass (관찰 → 매칭 → 추론 → 계산)
- **Stage 5:** deterministic decision tree + LLM reasoning only
- **Stage 6:** Knowledge DB에서 investigation protocol RAG
- **Pydantic 스키마:** 시간 여유 시 추가, 없으면 v4.1로 연기

---

## Phase 1: Knowledge DB 구축 (1시간)

### 1-1. 디렉토리 생성

```
knowledge/
  ddx_myocarditis.json         ← 심근염 감별진단 DB (7 subtypes)
  investigation_protocols.json ← 검사 프로토콜 DB (Stage 6용)
knowledge_loader.py            ← DB 로드 유틸리티
```

### 1-2. `ddx_myocarditis.json` — 핵심 구조

7개 subtype, 각 subtype별: primary_indicators, supporting_indicators, confirmatory.
각 indicator에 extraction_keywords(3B 매칭용), differentiation_guide(3C 추론용), weight(3D 계산용).

Phase 0에서 확인된 비결정성 케이스의 마커(rapid_heart_failure, positive_viral_pcr 등)에
특히 구체적인 differentiation_guide를 포함해야 함.

**스키마 예시 (GCM subtype):**

```json
{
  "version": "4.0",
  "subtypes": {
    "giant_cell_myocarditis": {
      "label": "Giant Cell Myocarditis",
      "pathophysiology": "Autoimmune-mediated destruction with multinucleated giant cells...",
      "clinical_features": {
        "primary_indicators": [
          {
            "finding": "new_onset_ventricular_arrhythmia",
            "description": "New VT/VF not explained by pre-existing arrhythmia",
            "extraction_keywords": ["ventricular tachycardia", "VT", "VF", "ventricular fibrillation", "arrhythmia", "palpitation"],
            "negative_keywords": ["sinus tachycardia", "SVT", "atrial fibrillation"],
            "differentiation_guide": "Must distinguish from: (1) baseline arrhythmia, (2) sinus tachycardia, (3) SVT. GCM-associated VT is typically polymorphic or sustained monomorphic.",
            "weight": 0.5
          },
          {
            "finding": "rapid_heart_failure",
            "description": "Rapidly progressive HF within days to weeks",
            "extraction_keywords": ["heart failure", "cardiomyopathy", "EF", "ejection fraction", "dyspnea", "pulmonary edema", "cardiogenic shock"],
            "differentiation_guide": "GCM progresses rapidly (days-weeks) despite standard therapy. Vaccine-induced is typically mild and self-limited with EF recovery.",
            "weight": 0.6
          }
        ],
        "supporting_indicators": [...],
        "confirmatory": [
          {
            "finding": "giant_cells_on_biopsy",
            "extraction_keywords": ["biopsy", "giant cell", "EMB", "endomyocardial"],
            "weight": 1.0,
            "is_gold_standard": true
          }
        ]
      },
      "high_suspicion_criteria": "new_onset_ventricular_arrhythmia AND (autoimmune_comorbidity OR treatment_non_response)"
    }
  }
}
```

7개 subtype 모두 작성: giant_cell, viral, eosinophilic, toxin_ici, ischemic, covid19, autoimmune.
+ narrative_nuance 섹션 (epistemic markers, NCI에서 제외됨을 명시).

### 1-3. `investigation_protocols.json` — Stage 6용

각 subtype별 검사 프로토콜 (test, priority, rationale, indication, impact).
v3.1 프롬프트에 하드코딩된 내용을 구조화하여 이동.

### 1-4. `knowledge_loader.py`

```python
import json
import os

def load_knowledge_db(base_path="knowledge"):
    with open(os.path.join(base_path, "ddx_myocarditis.json")) as f:
        ddx_db = json.load(f)
    with open(os.path.join(base_path, "investigation_protocols.json")) as f:
        protocols_db = json.load(f)
    return {"ddx": ddx_db, "protocols": protocols_db}
```

---

## Phase 2: Stage 3 Two-Pass 리팩토링 (2시간)

### Stage 1 vs Stage 3A 역할 구분 (중복 아님)

```
Stage 1 (ICSR Extractor): "무엇이 보고되었는가" — 데이터 추출
  → 정형 필드: 인적사항, 백신, 날짜, 검사 수치, 증상 목록
  → 예: troponin elevated=true, symptoms=["chest pain", "palpitations"]

Stage 3A (Clinical Observer): "이것이 임상적으로 무엇을 의미하는가" — 임상 해석
  → 비정형 해석: "pounding heart"가 VT인지 sinus tachycardia인지,
    "tachycardia since 1987"이 baseline인지 새로운 소견인지
  → keyword 매칭으로는 불가능한 의미 해석을 담당
  → Stage 3B(매칭)와 3C(추론)에 해석된 소견을 전달
```

### v4 아키텍처 (LLM 2회 + Code 2회 = 4단계)

```
Stage 3A (Clinical Observer) — LLM 1회
  Task: "이 소견이 임상적으로 무엇을 의미하는가?" (임상 해석)
  Input: 환자 narrative + Stage 1 ICSR output (구조화된 데이터 참조)
  Output: 카테고리별 해석된 소견 목록 + context (baseline 여부, 시점, 임상 의미)
  핵심: Stage 1의 데이터 추출과 다른 레벨 — 의미 해석이 목적

Stage 3B (DDx Matcher) — Code, Deterministic
  Task: 3A 소견을 DB의 extraction_keywords와 매칭
  Input: 3A output + ddx_myocarditis.json
  Output: DDx 후보 목록 (보통 1-3개) + 매칭 근거 + differentiation 질문
  핵심: 100% deterministic, 동일 입력 → 동일 출력

Stage 3C (Plausibility Assessor) — LLM 1회
  Task: 매칭된 2-3개 후보에 대해 집중 추론
  Input: 3A output + 3B 후보 + DB의 differentiation_guide
  Output: 후보별 present/plausibility/rationale
  핵심: LLM이 소수 후보만 판단 → attention 집중 → 재현성 향상

Stage 3D (NCI Calculator) — Code, Deterministic
  Task: v3.1 NCIEngine과 동일한 계산
  Input: 3C output + DB weights
  Output: NCI scores, WHO Step 1 conclusion, epistemic_uncertainty
```

### 파일 구조

```
pipeline/
  _legacy/
    stage3_v31.py                ← 현재 stage3_ddx_specialist.py 아카이브
  stage3a_clinical_observer.py   ← NEW
  stage3b_ddx_matcher.py         ← NEW
  stage3c_plausibility.py        ← NEW
  stage3d_nci_calculator.py      ← NEW (NCIEngine 이동)
```

### main.py 변경

```python
# v3.1
result["stages"]["stage3_ddx"] = run_stage3(llm, icsr, brighton, narrative)

# v4
stage3a = run_stage3a(llm, narrative)
stage3b = run_stage3b(stage3a, knowledge_db["ddx"])
stage3c = run_stage3c(llm, stage3a, stage3b, knowledge_db["ddx"])
stage3d = run_stage3d(stage3c, knowledge_db["ddx"])
result["stages"]["stage3_ddx"] = merge_stage3(stage3a, stage3b, stage3c, stage3d)
```

---

## Phase 3: Stage 5 리팩토링 (1시간)

### v4 아키텍처

```
Stage 5A (Decision Tree) — Code, Deterministic
  분류는 코드가 한다. 100% 재현성. Guard 불필요.
  
  if brighton > 3:           → Unclassifiable
  if max_nci >= 0.7:         → C
  if known_ae:
    if temporal_met:
      if max_nci >= 0.4:     → B2
      else:                  → A1
    else:
      if temporal UNLIKELY/BACKGROUND: → C
      else:                  → B2
  else:
    if temporal STRONG/PLAUSIBLE:
      if max_nci >= 0.4:     → B2
      else:                  → B1
    else:                    → C

Stage 5B (Reasoning Generator) — LLM 1회
  LLM은 이미 결정된 분류에 대한 설명만 생성.
  분류를 바꿀 수 없음.
```

### 핵심 변화
- v3.1의 `_apply_decision_guard()` 삭제 — decision tree가 이미 deterministic
- LLM hallucination이 분류에 영향 줄 수 없음

---

## Phase 4: Stage 6 리팩토링 (30분)

### 변경
- investigation_protocols.json에서 dominant alternative에 해당하는 protocol 가져옴
- 프롬프트 하드코딩 → DB 참조 (RAG)
- Lake Louise 71% → 100% 목표

```python
def run_stage6(llm, icsr, brighton, ddx, temporal, causality, knowledge_db):
    dominant = ddx.get("dominant_alternative")
    protocol = knowledge_db["protocols"].get(dominant, {})
    # protocol을 LLM context에 주입
```

---

## Phase 5: 나머지 정리 (30분)

- Stage 1, 2, 4: 변경 없음
- `knowledge_loader.py` 추가
- `config.py`에 Knowledge DB 경로 추가
- Pydantic 스키마: 시간 여유 시 추가, 없으면 v4.1

---

## Phase 6: 통합 테스트 (1.5시간)

### 6-1. 단일 케이스 (3건)
```bash
python main.py --case 1313197   # 비결정성 검증 (arrhythmia 인식?)
python main.py --case 1286607   # nuance 분리 유지 확인
python main.py --case 1386123   # nuance 분리 유지 확인
```

### 6-2. 전체 100건
```bash
python main.py
```
→ `results/results_v4.json`

### 6-3. 삼자 비교
- v3.0 vs v3.1 vs v4 분류 분포
- marker flip 횟수 비교 (비결정성 감소 측정)
- Stage 6 구체성 (EMB, viral panel, Lake Louise 출력률)

### 6-4. 재현성 테스트 (시간 여유 시)
- 1313197 3회 실행 → ventricular_arrhythmia 인식률 확인

---

## 예상 작업 시간

| Phase | 작업 | 시간 | 상태 |
|---|---|---|---|
| 0 | v3.1 결과 분석 | - | ✅ 완료 |
| 1 | Knowledge DB 구축 | 1시간 | 대기 |
| 2 | Stage 3 two-pass | 2시간 | 대기 |
| 3 | Stage 5 리팩토링 | 1시간 | 대기 |
| 4 | Stage 6 리팩토링 | 30분 | 대기 |
| 5 | 인프라 정리 | 30분 | 대기 |
| 6 | 통합 테스트 | 1.5시간 | 대기 |
| **합계** | | **~6.5시간** | |

---

## 수정 파일 목록

### 신규
```
knowledge/ddx_myocarditis.json
knowledge/investigation_protocols.json
knowledge_loader.py
pipeline/stage3a_clinical_observer.py
pipeline/stage3b_ddx_matcher.py
pipeline/stage3c_plausibility.py
pipeline/stage3d_nci_calculator.py
pipeline/_legacy/
```

### 수정
```
main.py
pipeline/stage5_causality_integrator.py
pipeline/stage6_guidance_advisor.py
prompts/system_prompts.py
config.py
```

### 보존
```
pipeline/stage1_icsr_extractor.py
pipeline/stage2_clinical_validator.py
pipeline/stage4_temporal_auditor.py
data_loader.py
llm_client.py
```

---

## 핵심 원칙

1. **관찰과 추론을 분리한다** — 1st pass는 "무엇이 있는가", 2nd pass는 "이것이 의미하는 것은"
2. **분류는 코드가 한다** — LLM은 관찰과 설명만 담당
3. **참고서를 따로 만든다** — Knowledge DB가 도메인 지식, LLM은 참조만
4. **각 agent는 하나의 일만 한다** — 과부하 금지
5. **재현성을 측정한다** — marker flip 횟수 추적
