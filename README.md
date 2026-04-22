# monthly_local_consumption

경기도 및 31개 시군의 지역화폐 **신규가입자수/충전액/사용액**을 조회·비교하는 Streamlit 대시보드입니다.

## 주요 기능

- 상단 안내(`ⓘ 안내`) 툴팁으로 서비스 설명/출처/한계/최종수정 정보 제공
- 타이틀 하단에 기준년월과 출처 표시
- 탭 구성
1. `경기도 현황`
: 월별 KPI 카드, 전체기간 최고/최저 카드, 월별 추이, 전년동월대비 추이
2. `시군별 현황`
: 시군별 사용액/충전액/신규가입자수 순위, 선택 시군 KPI 카드, 시군 월별 추이/전년동월대비 추이
3. `진단`
: 최근 연속 증가/감소, 전년동월 증감률(단월), 변동성(CV)

## 데이터 소스

- 경기데이터드림 Open API
- API: `RegionMnyPublctUse` (지역화폐 발행 및 이용 현황)
- DB 미사용, 앱 실행 시 API 직접 호출
- 페이지당 최대 1,000건, 병렬 호출/재시도 적용
- 세션 캐시 사용, 사이드바 `데이터 새로고침`으로 재로딩 가능

## 환경 변수 / Secrets

아래 값이 필요합니다.

- `APP_KEY`: 경기데이터드림 API 키
- `ACCESS_CODE`: 앱 접근 코드

`st.secrets` 또는 OS 환경변수(`APP_KEY`, `ACCESS_CODE`)로 설정할 수 있습니다.

## 실행 방법

```powershell
cd C:\Users\USER\Desktop\PY_FILES\monthly_local_consumption
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## 주요 지표 정의

- `CARD_PUBLCT_CNT`: 월별 신규가입자수
- `CARD_CHRGNG_AMT`: 월별 충전액(백만원)
- `CARD_USE_AMT`: 월별 사용액(백만원)
- `전년동월대비`: 동일 지표의 12개월 전 같은 월과 비교한 증감액/증감률

`CARD_PUBLCT_CNT`는 누적 가입자수가 아닌 **해당 월 신규가입자수**입니다.

## 한계

- 업종별/성별/연령별 데이터는 최신 데이터 부재로 본 대시보드 분석 범위에서 제외
