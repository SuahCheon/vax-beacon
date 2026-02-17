# Vax-Beacon v4.3 Execution Plan — Pending Clinical Data Override

**전제:** v4.2 완료 및 검증 후 실행 (Brighton Exit Guidance + Unclassifiable 표준화)
**목표:** Stage 2에서 "ordered/pending/not completed" 임상 데이터를 양성으로 오판하는 문제 수정
**성격:** Stage 2 Brighton 판정 정확도 개선. **WHO 분류 로직 변경 없음, Brighton 판정 정확도 변경.**

---

## Background

### 발견 경위
VAERS 1313197 케이스 분석 중 발견:
- Stage 1 LLM이 `cardiac_mri: "ordered but not completed"` 추출
- Stage 2가 이 문자열을 `cardiac_mri_positive = true`로 판정
- 실제로는 MRI가 수행되지 않았으므로 `false`가 정확

### 근본 원인
Stage 2의 free-text 임상 필드 판정 로직이 "not null + not normal + not negative" = positive로 처리.
"ordered", "pending", "not completed" 등 미완료 상태도 positive로 오분류.

### 영향 범위 (100-case 전수 스캔)

| VAERS ID | 필드 | 추출값 | 현재 판정 | 수정 후 | Brighton 변화 | WHO 변화 |
|----------|------|--------|-----------|---------|---------------|----------|
| 1313197 | cardiac_mri | "ordered but not completed" | positive=**true** | **false** | L3 → **L4** | A1/B2¹ → **Unclassifiable** |
| 1326494 | cardiac_mri | "pending" | positive=**true** | **false** | L1 → **L2** | A1 → A1 (불변) |
| 1430395 | echo_findings | "planned but results not available" | abnormal=**true** | **false** | L2 → L2 (불변) | B2 → B2 (불변) |

¹ 1313197은 NCI drift 케이스 (단독 실행 NCI=0.0/A1, 100-case NCI=0.5/B2).
L4로 변경 시 Stage 3-5 스킵 → NCI drift 자체가 해소됨.

### 예상 결과 요약
- Brighton 레벨 변경: **2건** (1313197: L3→L4, 1326494: L1→L2)
- WHO 분류 변경: **1건** (1313197 → Unclassifiable)
- Unclassifiable 증가: 23 → **24** (+1)
- NCI drift 해소: 1313197이 더 이상 비결정적 분류 안 함

---

## Phase 1: Stage 2 Pending Override 구현

### 1-1. `pipeline/stage2_clinical_validator.py`

**신규 함수 추가:** `_is_pending_status()`

```python
# --- Pending/Ordered status detection ---
PENDING_KEYWORDS = [
    "ordered", "pending", "not completed", "not yet",
    "scheduled", "awaiting", "planned", "requested",
    "to be done", "not available", "not performed",
    "not obtained", "awaited",
]

def _is_pending_status(value: str) -> bool:
    """Detect if a clinical data value indicates pending/ordered status.

    Returns True if the value describes a test that was ordered but
    not completed — should NOT be treated as a positive finding.
    """
    if not value:
        return False
    lower = value.lower().strip()
    return any(kw in lower for kw in PENDING_KEYWORDS)
```

### 1-2. 기존 판정 로직 수정

**cardiac_mri_positive:**
```python
# 기존:
mri = clinical.get("cardiac_mri")
mri_positive = (
    mri is not None
    and str(mri).strip() != ""
    and "normal" not in str(mri).lower()
    and "negative" not in str(mri).lower()
)

# 변경:
mri = clinical.get("cardiac_mri")
mri_str = str(mri).strip() if mri else ""
mri_positive = (
    mri is not None
    and mri_str != ""
    and "normal" not in mri_str.lower()
    and "negative" not in mri_str.lower()
    and not _is_pending_status(mri_str)       # ← NEW
)
```

**ecg_abnormal:**
```python
# 기존:
ecg = clinical.get("ecg_findings")
ecg_lower = str(ecg).lower() if ecg else ""
ecg_abnormal = (
    ecg is not None
    and str(ecg).strip() != ""
    and "normal" not in ecg_lower
    and "negative" not in ecg_lower
    and "unremarkable" not in ecg_lower
)

# 변경:
ecg = clinical.get("ecg_findings")
ecg_str = str(ecg).strip() if ecg else ""
ecg_lower = ecg_str.lower()
ecg_abnormal = (
    ecg is not None
    and ecg_str != ""
    and "normal" not in ecg_lower
    and "negative" not in ecg_lower
    and "unremarkable" not in ecg_lower
    and not _is_pending_status(ecg_str)       # ← NEW
)
```

**echo_abnormal:**
```python
# 기존:
echo = clinical.get("echo_findings")
echo_lower = str(echo).lower() if echo else ""
echo_abnormal = (
    echo is not None
    and str(echo).strip() != ""
    and "normal" not in echo_lower
    and "negative" not in echo_lower
    and "unremarkable" not in echo_lower
    and "no " not in echo_lower[:20]
)

# 변경:
echo = clinical.get("echo_findings")
echo_str = str(echo).strip() if echo else ""
echo_lower = echo_str.lower()
echo_abnormal = (
    echo is not None
    and echo_str != ""
    and "normal" not in echo_lower
    and "negative" not in echo_lower
    and "unremarkable" not in echo_lower
    and "no " not in echo_lower[:20]
    and not _is_pending_status(echo_str)      # ← NEW
)
```

### 1-3. Pending status 감사 로그 추가

`criteria_met`에 pending status 기록:

```python
# criteria_met dict에 추가
pending_flags = {}
if mri and _is_pending_status(str(mri)):
    pending_flags["cardiac_mri"] = str(mri)
if ecg and _is_pending_status(str(ecg)):
    pending_flags["ecg_findings"] = str(ecg)
if echo and _is_pending_status(str(echo)):
    pending_flags["echo_findings"] = str(echo)
```

Return dict에 추가:
```python
return {
    ...
    "pending_overrides": pending_flags if pending_flags else None,
}
```

### 1-4. 검증

```bash
python main.py --case 1313197
```

확인 항목:
- [ ] `cardiac_mri_positive` = false
- [ ] Brighton Level = 4
- [ ] `early_exit` = true
- [ ] `pending_overrides` = `{"cardiac_mri": "ordered but not completed"}`
- [ ] Stage 6 mode = "brighton_exit" (v4.2에서 구현한 Brighton Exit Guidance 작동)
- [ ] WHO = Unclassifiable

```bash
python main.py --case 1326494
```

확인 항목:
- [ ] `cardiac_mri_positive` = false
- [ ] Brighton Level = 2 (L1→L2, troponin+ECG+symptoms는 여전히 충족)
- [ ] WHO = A1 (불변)

---

## Phase 2: Version Bump + 100-Case Run

### 2-1. Version Bump

**`knowledge/ddx_myocarditis.json`:** version → "4.3"
**`knowledge/investigation_protocols.json`:** version → "4.3"

### 2-2. 100-Case Run

```bash
Get-ChildItem -Path . -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
python main.py
```

---

## Phase 3: 검증 스크립트 + 결과 분석

### 3-1. `compare_v42_v43.py`

비교 항목:

**1. Brighton Level 변화** (예상: 2건)
- 1313197: L3 → L4
- 1326494: L1 → L2
- 나머지 98건: 불변

**2. WHO 분류 변화** (예상: 1건)
- 1313197: (A1 or B2) → Unclassifiable
- 나머지 99건: 불변

**3. Unclassifiable 케이스 검증**
- 기존 Brighton L4 23건: guidance 유지 (regression 없음)
- 기존 Onset unknown 1건: guidance 유지 (regression 없음)
- 신규 1313197: Brighton Exit Guidance 존재 확인 (mode: "brighton_exit")
- 총 Unclassifiable: 24건

**4. Pending Override 감사**
- `pending_overrides` 필드 존재하는 케이스 목록 출력
- 각 케이스의 Brighton 변화 확인

**5. Non-Unclassifiable Regression**
- WHO 변경 없는 76건: Stage 6 output key 일치 확인

---

## 파일 변경 요약

| 파일 | 변경 | 위험도 |
|------|------|--------|
| `pipeline/stage2_clinical_validator.py` | `_is_pending_status()` 추가 + 3개 필드 판정에 pending 체크 추가 | **LOW** |
| `knowledge/ddx_myocarditis.json` | version bump → "4.3" | NONE |
| `knowledge/investigation_protocols.json` | version bump → "4.3" | NONE |
| `compare_v42_v43.py` | 비교 스크립트 신규 생성 | NONE |

**Stage 3/4/5/6 코드 변경: 없음.**
**프롬프트 변경: 없음.**
**Stage 2 Brighton 판정 로직만 수정 — pending 검사 결과를 양성으로 오판하지 않도록.**

---

## 실행 순서

Phase 1 (Pending Override 구현 + 단건 검증) → Phase 2 (Version Bump + 100-Case Run) → Phase 3 (비교 스크립트 + 결과 분석)

## 예상 소요

| Phase | 시간 |
|-------|------|
| Phase 1 | 30분 |
| Phase 2 | 1시간 (100-case run) |
| Phase 3 | 20분 |
| **합계** | **~2시간** |
