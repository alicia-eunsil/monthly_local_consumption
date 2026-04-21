# monthly_local_consumption

경기도 지역화폐 발행·이용 현황을 보는 Streamlit 대시보드입니다.

## 실행

```powershell
cd C:\Users\USER\Desktop\PY_FILES\monthly_local_consumption
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## 데이터 사용 방식

1차 버전은 DB를 사용하지 않습니다.

- 경기데이터드림 Open API 자동 호출
- 페이지당 최대 1,000건씩 병렬 호출
- 일시적 지연에 대비해 페이지별 재시도
- 첫 로딩 중 진행률 표시
- 세션 동안 로딩 결과를 재사용하며, 사이드바의 `데이터 새로고침` 버튼으로 다시 불러오기

사용 API:

- `RegionMnyPublctUse`: 지역화폐 발행 및 이용 현황
- `RegionMnyCard...`: 지역화폐 업종구분별 매출


## 화면 구성

- 요약: 월별 신규가입자수, 충전액, 사용액, 사용액/충전액 비율
- 월별 추이: 신규가입자수, 충전액, 사용액 추이와 전년동월대비 증감수/증감액/증감률
- 성연령별 매출: 월 선택, 성연령별 매출 Top N, 전월/전년동월대비 비교
- 시군별 현황: 시군별 사용액, 충전액, 신규가입자수 순위, 선택 시군 사용액·충전액 추이, 사용액 전년동월대비 증감률 순위

## 주요 지표

- `CARD_PUBLCT_CNT`: 월별 신규가입자수
- `CARD_CHRGNG_AMT`: 월별 충전액, 백만원
- `CARD_USE_AMT`: 월별 사용액, 백만원
- 전년동월대비: 선택한 시군 필터 기준으로 12개월 전 같은 월과 비교한 증감수, 증감액 및 증감률

`CARD_PUBLCT_CNT`는 누적 가입자수가 아니라 해당 월 신규가입자수입니다.
