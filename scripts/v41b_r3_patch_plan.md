# v4.1b-r3 Patch Plan — MRI Framing + Nucleocapsid Routing

**목표:** v4.1b-r2 검증에서 발견된 잔여 이슈 2건 수정
**성격:** Stage 6 output quality 패치. WHO 분류 로직 변경 없음.

---

## Issue 1: MRI "vaccine vs viral" Framing (2건)

### 현상
VAERS 1326494, 1464592에서 Stage 6 output에 "vaccine vs viral" MRI framing 발견.
현재 프롬프트에 `NOT "vaccine vs viral pattern differentiation"` 규칙이 있으나 LLM이 무시.

### 원인 분석
프롬프트에 1줄 규칙만 있고, **왜 안 되는지** 임상 근거가 없음.
LLM은 "하지 마라"보다 "대신 이렇게 해라 + 이유"에 더 잘 반응.

### 수정

**File:** `prompts/system_prompts.py` — `STAGE6_GUIDANCE_ADVISOR`

기존:
```
- Frame cardiac MRI as "GCM/ischemic exclusion + involvement extent assessment",
  NOT "vaccine vs viral pattern differentiation"
```

교체:
```
CARDIAC MRI FRAMING POLICY (MANDATORY):
- NEVER frame MRI as "vaccine-induced vs viral myocarditis differentiation"
  or "distinguish vaccine from viral etiology" — this is clinically INVALID.
  Both vaccine-induced and viral myocarditis are lymphocytic and produce
  overlapping Late Gadolinium Enhancement patterns on MRI.
  Lake Louise criteria CANNOT reliably distinguish between them.
- ALWAYS frame MRI recommendations as ONE OR MORE of:
  (a) Confirm myocardial inflammation presence (Lake Louise criteria)
  (b) Assess myocardial involvement extent (focal vs diffuse)
  (c) Exclude GCM (diffuse mid-wall LGE pattern)
  (d) Exclude ischemic etiology (subendocardial LGE pattern)
- If MRI was already performed, report its actual findings without
  framing them as "consistent with vaccine" or "consistent with viral"
```

### 검증
- VAERS 1326494, 1464592 재실행
- 100-case run에서 "vaccine vs viral" string 검색 → 0건 확인

---

## Issue 2: COVID Non-Dominant Nucleocapsid Recommendation (10건 누락)

### 현상
- COVID dominant 2건: nucleocapsid 권고 2/2 (100%)
- COVID suspect but non-dominant 10건: nucleocapsid 권고 0/10 (0%)

### 원인 분석
현재 Stage 6 routing은 `dominant_alternative`에 해당하는 protocol만 주입.
COVID가 dominant가 아니면 (예: viral이 dominant) COVID protocol이 주입되지 않음 →
nucleocapsid 검사 권고가 나올 수 없는 구조.

### 수정 방향
Dominant protocol 외에, **COVID가 suspect인 경우** nucleocapsid 권고를 supplementary로 추가.

**File:** `pipeline/stage6_guidance_advisor.py`

`_run_normal()` 함수에서 protocol 주입 로직 확장:

```python
# 기존: dominant protocol만 주입
protocol = _get_protocol_for_dominant(dominant, protocols_db)

# 추가: COVID suspect이면 nucleocapsid supplementary 주입
covid_supplement = ""
if _has_covid_suspect(ddx_data) and dominant_key != "covid19_related":
    covid_supplement = _format_covid_nucleocapsid_supplement()
```

**새 함수 추가:**

```python
def _has_covid_suspect(ddx_data: dict) -> bool:
    """Check if active_covid19 marker is present (any plausibility)."""
    if not ddx_data:
        return False
    etiologies = ddx_data.get("alternative_etiologies", {})
    covid = etiologies.get("covid19_related", {})
    indicators = covid.get("primary_indicators", [])
    for ind in indicators:
        if ind.get("finding") == "active_covid19" and ind.get("present"):
            return True
    return False

def _format_covid_nucleocapsid_supplement() -> str:
    """Return supplementary nucleocapsid guidance for non-COVID-dominant cases."""
    return (
        "\n=== SUPPLEMENTARY: COVID-19 DIFFERENTIATION ===\n"
        "COVID-19 infection was detected in this patient's history.\n"
        "Even though COVID-19 is not the dominant alternative etiology,\n"
        "nucleocapsid antibody testing is recommended to differentiate\n"
        "natural infection from vaccination-only immune response.\n"
        "mRNA vaccines produce only spike protein antibody, NOT nucleocapsid.\n"
        "Positive nucleocapsid = prior natural infection confirmed.\n"
        "Include nucleocapsid antibody test in investigative gaps.\n"
        "=== END SUPPLEMENTARY ===\n"
    )
```

**프롬프트 주입:** `{protocol_context}` 뒤에 covid_supplement 추가.

### 검증
- COVID suspect non-dominant 케이스 2-3건 재실행
- nucleocapsid 권고 포함 확인
- 100-case run에서 COVID suspect 케이스 중 nucleocapsid 권고 비율 확인

---

## Phase 3: 100-Case 검증

```bash
find . -type d -name __pycache__ -exec rm -rf {} +
python main.py
```

### 검증 항목
1. **WHO 분류 변화 0건** (output quality 패치이므로 분류 불변)
2. MRI "vaccine vs viral" framing: 0건
3. COVID suspect nucleocapsid 권고: dominant 100% + non-dominant에서 개선
4. 기존 메트릭 유지: Bridging 100%, Scope 단조성, etc.

### 비교 스크립트
`compare_v41b_r2_r3.py` — r2 vs r3 diff만 추출 (Stage 6 output만 비교)

---

## 파일 변경 요약

| 파일 | 변경 | 위험도 |
|------|------|--------|
| `prompts/system_prompts.py` | MRI framing 규칙 강화 | LOW |
| `pipeline/stage6_guidance_advisor.py` | COVID supplement routing 추가 | LOW |
| `knowledge/ddx_myocarditis.json` | version bump → v4.1b-r3 | NONE |
| `knowledge/investigation_protocols.json` | version bump → v4.1b-r3 | NONE |

**분류 로직 변경: 없음. Stage 3/4/5 코드 변경: 없음.**
