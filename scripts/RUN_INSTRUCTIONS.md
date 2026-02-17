# Claude Code 실행 지시어

아래 명령을 Claude Code 터미널에서 순서대로 실행하세요.

## 1. 프로젝트 디렉토리로 이동
```bash
cd /mnt/c/vska_original/data/vaers/vax-beacon
```

## 2. 추출 스크립트 실행
```bash
python3 scripts/extract_cohort.py
```

## 3. 결과 확인
```bash
# 파일 생성 확인
ls -lh data/vaers_100_cohort.csv

# 행 수 확인 (헤더 포함 101줄이면 정상)
wc -l data/vaers_100_cohort.csv

# 컬럼 확인
head -1 data/vaers_100_cohort.csv | tr ',' '\n' | cat -n

# 첫 3건 미리보기
head -4 data/vaers_100_cohort.csv | python3 -c "
import csv, sys
reader = csv.DictReader(sys.stdin)
for row in reader:
    print(f\"ID={row['VAERS_ID']} | {row['condition_type']} | {row['group']} | onset={row['curated_onset_days']}d\")
"
```

## 트러블슈팅
- `ModuleNotFoundError` → 순수 표준 라이브러리(csv, json, os)만 사용하므로 발생하지 않아야 함
- `FileNotFoundError` → WSL 경로가 다를 수 있음. `ls /mnt/c/vska_original/data/vaers/vaers_jan_nov_2021.csv/` 로 원본 위치 확인
- 인코딩 에러 → 스크립트에 `errors="replace"` 이미 적용됨
