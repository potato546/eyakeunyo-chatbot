# 약물 정보 챗봇 (e약은요 + DUR API)

## 1. 구조
```
eyakeunyo_chatbot/
├── app.py              # Flask 백엔드 (API 호출 + 로직)
├── templates/index.html # 채팅창 UI
├── requirements.txt
├── .env.example        # 인증키 넣는 곳 (복사해서 .env로 사용)
└── README.md
```

브라우저 ↔ Flask 서버 ↔ 공공데이터포털(data.go.kr) 구조입니다.
공공데이터 API는 브라우저에서 직접 호출하면 CORS/키 노출 문제가 있어서,
Flask가 중간에서 대신 호출해주는 방식(프록시)으로 만들었습니다.

## 2. 실행 방법
```bash
cd eyakeunyo_chatbot
pip install -r requirements.txt
cp .env.example .env
# .env 파일을 열어서 DATA_GO_KR_SERVICE_KEY 값에 본인 인증키 붙여넣기
python app.py
```
브라우저에서 http://localhost:5000 접속

**인증키 주의**: data.go.kr 마이페이지에는 인증키가 "Encoding"과 "Decoding" 두 버전으로
나옵니다. 이 코드는 `requests`의 `params=` 방식으로 자동 인코딩을 하기 때문에,
반드시 **Decoding(일반 인증키)** 버전을 넣어야 합니다. Encoding 키를 넣으면
`+`, `/` 같은 문자가 이중 인코딩되어 인증 오류가 날 수 있어요.

**인증키가 2개(e약은요용, DUR용)인 경우**: data.go.kr은 보통 계정 하나당 인증키 하나를
여러 API에 공용으로 씁니다. 먼저 두 키 문자열이 실제로 같은지 확인해보세요.
- **같으면** → `DATA_GO_KR_SERVICE_KEY` 하나만 채우면 끝
- **다르면** → `.env`에 아래 두 줄을 추가로 채우세요 (코드가 자동으로 우선 사용합니다)
  ```
  DATA_GO_KR_EASY_KEY=e약은요_전용_키
  DATA_GO_KR_DUR_KEY=DUR_전용_키
  ```

## 3. 기능별 매핑

| 요청하신 기능 | 사용 API | 비고 |
|---|---|---|
| 성분명/제품명으로 약 정보 조회 | 의약품개요정보(e약은요) `DrbEasyDrugInfoService/getDrbEasyDrugList` | **제품명 기준 검색만 지원**됩니다. 성분명(예: 아세트아미노펜)으로 검색하면 결과가 안 나올 수 있어요 — 이 API 자체가 `itemName`(제품명), `entpName`(업체명) 파라미터만 받고 성분명 파라미터는 없습니다. 성분명 검색이 꼭 필요하면 "의약품 제품 허가정보" API(성분 정보 포함)를 추가로 붙이는 걸 추천드려요. |
| 여러 약물 상호작용/부작용 | DUR품목정보서비스 `DURPrdlstInfoService03/getUsjntTabooInfoList03` (병용금기) | 약물 A로 조회해서 나오는 병용금기 목록 안에 약물 B 이름이 들어있는지 텍스트로 대조하는 방식이에요. |
| 복용 횟수/일수 적합 여부 | DUR `getMdctnPdAtentInfoList03`(투여기간주의), `getCpctyAtentInfoList03`(용량주의) | ⚠️ 이 API들은 대부분 "최대 7일까지" 같은 **서술형 문구**로 데이터를 주기 때문에, 입력한 횟수/일수와 자동으로 비교해서 O/X를 딱 잘라 판정하기는 어려워요. 코드에서는 관련 문구를 그대로 보여주고, 최종 판단은 약사가 하도록 설계했습니다. |

## 4. 꼭 확인해야 할 것 (중요)

이 개발 환경에서는 네트워크 제약상 `apis.data.go.kr`에 직접 접속해서
테스트 호출을 해볼 수가 없었어요. 그래서 `app.py`의 e약은요 부분(효능/사용법/
상호작용/부작용 필드명)은 공식 문서에서 확인한 정확한 값이지만,
DUR 쪽 오퍼레이션 이름 중 일부(`getSpcifyAgeTabooInfoList03`, `getPwnmTabooInfoList03`,
`getCpctyAtentInfoList03`, `getMdctnPdAtentInfoList03`, `getOdsnAtentInfoList03`,
`getEfcyDplctInfoList03`)는 **실제 Swagger 명세와 다를 수 있습니다.**

처음 실행 후 아래 순서로 확인해주세요:

1. 브라우저에서 `http://localhost:5000/api/debug/raw?op=usjnt_taboo&itemName=타이레놀정500밀리그램` 접속
   → 정상 응답이 오는지 확인 (병용금기는 확인된 오퍼레이션이라 여기는 바로 될 확률이 높아요)
2. data.go.kr에서 "의약품안전사용서비스(DUR)품목정보" 상세페이지 > **상세기능정보** 탭 또는
   Swagger UI에서 정확한 오퍼레이션명 확인
3. 만약 `app.py`의 `DUR_OPERATIONS` 딕셔너리에 있는 이름과 다르면, 거기 값만 고쳐주면 됩니다
   (다른 코드는 안 건드려도 돼요 — 응답 필드도 이름을 미리 못 박지 않고 레코드 전체를
   텍스트로 검사하도록 만들어놔서, 필드명이 좀 달라도 병용금기 체크(기능 2)는 잘 동작할 확률이 높습니다).

## 5. 모바일에서 접속하기

### 방법 A. 집 와이파이 안에서 (돈 안 들고 가장 간단)
1. `python app.py`로 컴퓨터에서 서버 실행 (이미 `host="0.0.0.0"`으로 설정되어 있어 외부 접속 허용됨)
2. 컴퓨터의 로컬 IP 확인
   - Mac: 시스템 설정 > Wi-Fi > 세부사항, 또는 터미널에서 `ipconfig getifaddr en0`
   - Windows: cmd에서 `ipconfig` 실행 후 "IPv4 주소" 확인 (예: 192.168.0.12)
3. 휴대폰을 **같은 와이파이**에 연결한 뒤, 브라우저에서 `http://192.168.0.12:5000` 접속
4. 컴퓨터를 끄면 당연히 챗봇도 꺼져요 — 컴퓨터가 켜져 있어야 합니다.

방화벽 때문에 안 열리면 (Windows Defender 방화벽에서 Python 허용해야 할 수 있어요),
또는 공유기 설정에 따라 안 될 수도 있어요.

### 방법 B. Render.com에 배포해서 어디서든 접속되게 하기

`render.yaml`, `Procfile`, `gunicorn`까지 이미 준비해뒀어요. 아래 순서대로 하면 됩니다.

**1) GitHub에 코드 올리기**
```bash
cd eyakeunyo_chatbot
git init
git add .
git commit -m "약물 정보 챗봇 초기 버전"
```
GitHub에서 새 저장소(예: `eyakeunyo-chatbot`)를 만든 뒤:
```bash
git remote add origin https://github.com/본인아이디/eyakeunyo-chatbot.git
git branch -M main
git push -u origin main
```
`.gitignore`에 `.env`가 들어있어서 인증키는 깃허브에 올라가지 않아요. (안심하고 push 하세요)

**2) Render.com 가입 및 연결**
1. https://render.com 가입 (GitHub 계정으로 로그인 가능)
2. 대시보드에서 **New +** → **Blueprint** 선택
3. 방금 만든 GitHub 저장소 선택 → Render가 `render.yaml`을 자동으로 인식해서
   서비스 설정을 미리 채워줘요 (Web Service, Python, gunicorn 명령까지 자동 설정됨)
4. `DATA_GO_KR_SERVICE_KEY` 값을 입력하라는 칸이 나오면, 본인의 **Decoding(일반) 인증키**를 붙여넣기
5. **Apply** / **Create Web Service** 클릭 → 몇 분 기다리면 빌드+배포 완료

**3) 완성된 주소로 접속**
배포가 끝나면 `https://eyakeunyo-chatbot.onrender.com` 같은 주소가 생겨요.
이 주소를 휴대폰 브라우저에서 열면 바로 챗봇이 뜹니다 (와이파이/데이터 상관없이 접속 가능).
휴대폰 홈 화면에 "바로가기"로 추가해두면 앱처럼 아이콘 눌러서 쓸 수 있어요
(Safari: 공유 버튼 > 홈 화면에 추가 / Chrome: 메뉴 > 홈 화면에 추가).

**참고 (무료 플랜 특성)**
- Render 무료 플랜은 일정 시간 요청이 없으면 서버가 "잠들어요(sleep)". 오랜만에 접속하면
  첫 응답이 20~30초 정도 느릴 수 있는데, 정상입니다 (서버가 깨어나는 중).
- 무료 플랜은 매달 750시간 무료 — 챗봇 하나 정도는 24시간 켜둬도 충분해요.

**4) 코드 수정 후 다시 배포하려면**
로컬에서 코드 고친 뒤:
```bash
git add .
git commit -m "수정 내용"
git push
```
Render가 GitHub push를 감지해서 자동으로 재배포합니다.

## 6. 개선 아이디어 (원하시면 다음 단계로 추가해드릴 수 있어요)
- 성분명 검색 지원 (의약품 제품 허가정보 API 연동)
- itemSeq(품목기준코드) 기반 정밀 매칭 (동명이인 제품 구분)
- 특정연령대금기/임부금기/노인주의까지 상호작용 체크에 포함
- 응답 캐싱 (같은 약 반복 조회 시 API 호출 절약)
- 대화 이력 저장 (지금은 새로고침하면 대화가 사라짐)
