# monthly_local_consumption

경기도 지역화폐 월별 소비·운영 현황을 보는 Streamlit 대시보드입니다.

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
- Streamlit `cache_data`로 읽기/정규화 결과를 6시간 캐시

사용 API:

- `TB25BPTGGCARDCATMSALEM`: 카드업종중분류 지역화폐 업종구분별 매출
- `RegionMnyPublctUse`: 지역화폐 발행 및 이용 현황

## APP_KEY 설정

현재 앱은 경기데이터드림 Open API를 데이터 소스로 사용합니다. `APP_KEY`는 필수입니다.

Streamlit Cloud에서는 App settings > Secrets 또는 Environment variables에 다음 값을 설정하세요.

```toml
APP_KEY = "YOUR_GGDATA_APP_KEY"
ACCESS_CODE = "YOUR_ACCESS_CODE"
```

로컬 PowerShell에서는:

```powershell
$env:APP_KEY="YOUR_GGDATA_APP_KEY"
$env:ACCESS_CODE="YOUR_ACCESS_CODE"
streamlit run app.py
```

`ACCESS_CODE`가 설정되어 있으면 앱 첫 화면에서 접속코드를 요구합니다. 설정하지 않으면 접속코드 없이 실행됩니다.

## 화면 구성

- 요약: 총 매출, 월별 신규가입자수, 충전액, 사용액, 월별 추이
- 업종·지역: 업종별 매출 순위, 지역별 매출 순위, 지역 x 업종 히트맵
- 운영 현황: 시군별 사용액/충전액 순위, 신규가입자수 추이

## 주요 지표

- `SALES_AMT`: 지역화폐 업종별 매출금액
- `CARD_PUBLCT_CNT`: 월별 신규가입자수
- `CARD_CHRGNG_AMT`: 월별 충전액, 백만원
- `CARD_USE_AMT`: 월별 사용액, 백만원

`CARD_PUBLCT_CNT`는 누적 가입자수가 아니라 해당 월 신규가입자수입니다.
