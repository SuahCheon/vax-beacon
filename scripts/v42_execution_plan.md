# Vax-Beacon v4.2 Execution Plan — Brighton Exit Guidance

**전제:** v4.1b-r3 패치 완료 및 검증 후 실행
**목표:** Brighton Level 4 early exit 케이스에 조사관용 actionable guidance 제공
**성격:** Output quality 개선. WHO 분류 로직 변경 없음.

---

## Background

현재 Brighton Level 4 (진단 근거 부족) 케이스는:
- Stage 1 → Stage 2 (Brighton 4) → STOP → "Unclassifiable" 출력
- Stage 3/4/5/6 모두 스킵
- 조사관은 "왜 분류 불가인지", "다음에 뭘 해야 하는지" 안내 없음

v4.2 이후:
- Stage 1 → Stage 2 (Brighton 4) → **Stage 6 (Brighton Guidance Mode)** → "Unclassifiable" + guidance
- 조사관에게 누락된 Brighton 기준, 필요한 검사, 우선순위 안내

---

## Phase 1: Brighton Exit Guidance 구현

### 1-1. `pipeline/stage6_guidance_advisor.py`

**새 함수 추가:** `_run_brighton_exit()`

```python
def _run_brighton_exit(llm, icsr_data: dict, brighton_data: dict) -> dict:
    """Brighton Level 4 early exit — 진단 근거 부족 시 guidance 생성."""
    criteria = brighton_data.get("criteria_met", {})
    condition = brighton_data.get("condition_type", "myocarditis")
    missing = _identify_missing_brighton_criteria(criteria, condition)
    
    prompt = STAGE6_BRIGHTON_EXIT.format(
        condition_type=condition,
        brighton_level=brighton_data.get("brighton_level"),
        criteria_met=json.dumps(criteria, indent=2),
        missing_criteria=json.dumps(missing, indent=2),
        narrative_summary=icsr_data.get("event", {}).get("narrative_summary", ""),
    )
    
    response = llm.generate(prompt)
    result = _parse_brighton_guidance(response)
    result["mode"] = "brighton_exit"
    return result
```

**새 함수 추가:** `_identify_missing_brighton_criteria()`

Myocarditis와 pericarditis 각각에 대해 Brighton Level 1-3 달성에 필요한 누락 기준 식별.
(세부 구현은 첨부한 v4.2 원본 문서의 Phase 1 → 1-2 섹션 참조)

### 1-2. `prompts/system_prompts.py`

**기존 `STAGE6_EARLY_EXIT` 프롬프트 확인 후 필요시 교체/보강.**

현재 `STAGE6_EARLY_EXIT`가 이미 존재하지만, Brighton-specific guidance에 최적화되어 있는지 확인.
필요하면 `STAGE6_BRIGHTON_EXIT` 프롬프트 신규 추가:
- 누락된 Brighton 기준 명시
- 각 기준에 대한 구체적 검사 권고 (troponin, ECG, Echo, MRI, EMB)
- 우선순위별 정렬
- 대안 진단 가능성 언급 (증상이 심근염이 아닐 수 있는 경우)

### 1-3. `main.py` — Brighton exit routing 변경

```python
if stage2_result.get("early_exit"):
    # 기존: Stage 6 스킵
    # 변경: Stage 6 Brighton guidance mode 실행
    stage6_result = run_stage6_brighton_exit(llm, stage1_result, stage2_result)
    result["stages"]["stage6_guidance"] = stage6_result
```

### 1-4. 검증

Brighton 4 케이스 실행:
- `--case 1088210` (G3, ECMO/Impella/Fulminant)
- `--case 1321207` (G1, Classic)

확인 항목:
- [ ] Stage 6 output 존재 (mode: "brighton_exit")
- [ ] 누락 기준 정확히 식별
- [ ] 권고 검사가 구체적이고 actionable
- [ ] WHO는 여전히 Unclassifiable

---

## Phase 2: Unclassifiable Output 표준화

### 2-1. 모든 Unclassifiable 경로의 output 통일

현재 Unclassifiable 발생 경로:
1. Brighton Level 4 early exit
2. Onset unknown (v4.1에서 추가)

두 경로 모두 동일한 output 구조:

```json
{
  "who_category": "Unclassifiable",
  "unclassifiable_reason": "brighton_insufficient | onset_unknown",
  "what_is_known": "이용 가능한 증거 요약",
  "what_is_missing": ["누락 정보 목록"],
  "recommended_actions": ["우선순위별 다음 단계"],
  "reassessment_potential": "누락 정보 확보 시 재평가 가능성"
}
```

### 2-2. 검증

Before/After 비교:
- Before: `{"who_category": "Unclassifiable"}` (guidance 없음)
- After: Full guidance + actionable next steps

---

## Phase 3: 100-Case 검증

```bash
find . -type d -name __pycache__ -exec rm -rf {} +
python main.py
```

### 검증 항목

1. **WHO 분류 분포 불변** — A1/B1/B2/C 건수 동일 (Unclassifiable도 동일)
2. **Unclassifiable 케이스에 guidance 존재** — Stage 6 output 확인
3. **기존 케이스 regression 없음** — non-Unclassifiable 케이스의 Stage 6 출력 불변

### 비교 스크립트

`compare_v41b_r3_v42.py`:
- WHO 분포 비교 (동일해야 함)
- Unclassifiable 케이스의 Stage 6 output 비교 (r3: 없음, v4.2: 있음)
- Non-Unclassifiable 케이스의 Stage 6 output diff (없어야 함)

---

## 파일 변경 요약

| 파일 | 변경 | 위험도 |
|------|------|--------|
| `pipeline/stage6_guidance_advisor.py` | `_run_brighton_exit()` 추가 | LOW |
| `prompts/system_prompts.py` | Brighton exit 프롬프트 추가/보강 | LOW |
| `main.py` | Brighton exit → Stage 6 routing | LOW |
| `config.py` | VERSION → "4.2" | NONE |

**분류 로직 변경: 없음. Stage 3/4/5 코드 변경: 없음.**

---

## 실행 순서

Phase 1 (Brighton Exit Guidance) → Phase 2 (Output 표준화) → Phase 3 (100-Case 검증)

## 예상 소요

| Phase | 시간 |
|-------|------|
| Phase 1 | 1시간 |
| Phase 2 | 20분 |
| Phase 3 | 1시간 (100-case run + 검증) |
| **합계** | **~2.5시간** |
