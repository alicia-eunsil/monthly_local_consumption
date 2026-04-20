# monthly_local_consumption

경기도 지역화폐 월별 소비/매출 현황을 보는 Streamlit 대시보드입니다.

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

- 화면에서 CSV 업로드
- 또는 `data/` 폴더에 CSV 저장 후 앱에서 선택
- Streamlit `cache_data`로 읽기/정규화 결과를 캐시

## APP_KEY 설정

현재 CSV 기반 MVP는 `APP_KEY` 없이도 실행됩니다. 이후 경기데이터드림 Open API 수집 기능을 붙이면 아래 값을 사용합니다.

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

권장 시작 데이터:

- `경기도_카드업종중분류_지역화폐 업종구분별 매출`

선택 데이터:

- `경기도_카드업종소분류_지역화폐 업종구분별 매출`
- `지역화폐_지역별_지도형태`

## 기대 컬럼

앱은 아래 한국어 컬럼 후보를 자동 인식합니다.

- 기준년월
- 읍면동코드
- 읍면동명 또는 지역명
- 중분류업종코드
- 중분류업종명 또는 업종명
- 매출금액
- 전월대비증감값, 전월대비증감률
- 전년동월대비증감값, 전년동월대비증감률

컬럼명이 다르면 `src/data.py`의 `COLUMN_ALIASES`에 후보명을 추가하면 됩니다.
