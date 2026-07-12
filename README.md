# corporate-finance-bot

배포 URL: https://corporate-finance-bot-web.onrender.com

재무관리 질문을 처리하기 위한 RAG + LLM + Python 계산 Tool 기반 챗봇입니다.
재무관리 이론 질의, 계산형 문제, KOSDAQ 재무제표 기반 기업 분석, DART/뉴스 원문 기반 추이 분석, 단순 재무 전망, 주가 추이와 백테스팅 통계 계산을 지원합니다.

구현 순서와 백엔드/프론트엔드/미들웨어 구성 요약은 `DEVELOPMENT_SUMMARY.md`에 정리되어 있습니다.

## Structure

```text
frontend/
├── package.json                   # Vite + React 프론트엔드 실행 스크립트
├── index.html                     # Vite 진입 HTML
├── chat_ui.jsx                    # 기존 단일 파일 채팅 UI
└── src/
    ├── main.jsx                   # React 앱 진입점
    ├── ChatUI.jsx                 # 사용자가 질문을 입력하고 답변을 확인하는 채팅 UI
    └── styles.css                 # 프론트엔드 스타일

backend/
├── server.py                      # FastAPI 서버, 프론트엔드 요청을 받아 main_agent로 전달
├── main_agent.py                  # 질문 유형 판단, RAG 검색, Tool 실행을 조율하는 메인 라우터
├── llm_client.py                  # 계산 결과와 검색 근거를 최종 답변 문장으로 정리하는 LLM 연결 지점
├── chart_builder.py               # 재무 추이, 전망, 주가 데이터를 프론트 차트 스펙으로 변환
├── dart_client.py                 # DART 사업보고서 원문 수집 클라이언트
├── news_client.py                 # 네이버 뉴스 수집 클라이언트
├── requirements.txt               # 백엔드 실행에 필요한 Python 패키지 목록
├── SKILL.md                       # 백엔드 RAG, LLM, Tool 역할 요약
├── company_data/
│   └── financial_store.py         # KOSDAQ 엑셀을 SQLite 캐시로 변환하고 회사/계정 조회 제공
├── data/
│   └── account_mapping.json       # 주요 재무계정 매핑 규칙
├── scripts/
│   ├── import_financial_excel.py  # KOSDAQ 엑셀을 backend/data/financials.sqlite로 적재
│   ├── fetch_dart_report.py       # DART 사업보고서를 외부문서 RAG용 텍스트로 저장
│   └── fetch_news.py              # 뉴스 검색 결과를 외부문서 RAG용 텍스트로 저장
├── rag/
│   ├── simple_rag.py              # knowledge 문서에서 질문과 관련된 기준을 검색하는 간단한 RAG
│   └── external_rag.py            # 사업보고서/뉴스 등 외부 텍스트 문서 검색
├── knowledge/
│   ├── corporate_finance_policy.md # 재무관리 답변과 계산의 기본 정책
│   ├── finance_basics.md           # 조달과 운용, 재무관리 목표, 자본비용 기초 개념
│   ├── time_value_of_money.md       # 현재가치, 미래가치, 연금, 실효이자율 기준
│   ├── capital_budgeting.md        # NPV, IRR, 회수기간 등 투자안 평가 기준
│   ├── cost_of_capital.md          # WACC, CAPM, 할인율 관련 기준
│   ├── financial_ratios.md         # 유동비율, 부채비율, ROE 등 재무비율 기준
│   ├── portfolio_theory.md         # 포트폴리오 기대수익률, 분산, 공분산, 상관계수 기준
│   ├── risk_return.md              # 위험 태도, 기대효용, 전망이론 기준
│   ├── working_capital.md          # 운전자본과 현금전환주기 기준
│   ├── mergers_acquisitions.md     # M&A 개념과 계산 기준
│   ├── valuation.md                # DCF, 배당할인모형, 주식가치, 배수평가 기준
│   └── report_templates.md         # 재무관리 답변 문장 템플릿
└── tools/
    ├── capital_budgeting_tool.py  # NPV와 투자안 평가 계산
    ├── cost_of_capital_tool.py    # WACC와 자본비용 계산
    ├── finance_concept_tool.py    # 재무관리 기초 개념 설명
    ├── financial_ratio_tool.py    # 주요 재무비율 계산
    ├── company_analysis_tool.py   # KOSDAQ 재무제표 주요 계정과 비율 조회
    ├── company_trend_tool.py      # 재무제표, 수익성 비율 추이와 외부문서 근거 기반 해석
    ├── forecast_tool.py           # 최근 재무 추이 기반 단순 전망 계산
    ├── mergers_acquisitions_tool.py # M&A 개념과 주요 계산
    ├── portfolio_tool.py          # 포트폴리오 기대수익률, 분산, 공분산 계산
    ├── risk_utility_tool.py       # 위험 태도, 기대효용, 전망이론, 보험료 계산
    ├── stock_price_tool.py        # Yahoo Finance 주가 조회, 수익률/표준편차/MDD 계산
    ├── time_value_tool.py         # 화폐의 시간가치 계산
    ├── valuation_tool.py          # 배당할인모형과 주식가치 계산
    └── working_capital_tool.py    # 운전자본과 현금전환주기 계산
```

## Features

- 재무제표 조회: 기업명이나 종목코드로 주요 계정, 재무비율, 연도별 추이를 조회합니다.
- 수익성 비율 추이: 매출액영업이익률, 매출액순이익률 등 비율 지표를 계산하고 `%` 차트로 표시합니다.
- 단순 전망: 최근 5개년 재무 추이를 바탕으로 CAGR, 선형 추세, 최근 성장률 가중평균을 비교해 보수/기준/낙관 전망을 제공합니다.
- 주가 분석: Yahoo Finance에서 일별 종가를 조회해 주가 차트, 기간 수익률, 평균, 표준편차, 연율화 변동성, 최대낙폭(MDD)을 계산합니다.
- 뉴스 우선 근거: 기업/주가/최근 실적 질문은 Naver News 근거를 먼저 확인한 뒤 답변에 반영합니다.
- 답변 UI: 그래프, 수식 렌더링, 답변 접기, 복사, 좋아요/비추천, 처리 과정 표시를 지원합니다.

## Data

커밋용 재무제표 데이터는 용량을 줄이기 위해 2019~2025년의 재무상태표, 손익계산서, 현금흐름표만 포함합니다.

- `KOSDAQ_financial_statements.xlsx`: 커밋 대상 축소본입니다. 포함 시트는 `2019_BS`~`2025_CF`이며 자본변동표(`*_CE`)는 제외합니다. 파일 크기를 줄이기 위해 회사/시장/업종/계정/당기 금액 조회에 필요한 최소 컬럼만 유지합니다.
- `KOSDAQ_financial_statements.full.xlsx`: 로컬 전용 전체 원본 백업 파일입니다.
- `backend/data/financials.sqlite`: 엑셀에서 생성되는 로컬 캐시이며 git에 커밋하지 않습니다.
- `backend/data/financials.sqlite.gz`: 배포용 압축 SQLite 캐시입니다. Render에서 첫 재무제표 질문이 엑셀 파싱 때문에 느려지는 문제를 줄이기 위해 커밋합니다.
- `backend/data/account_mapping.json`: 주요 계정 추출 규칙이므로 git에 커밋합니다.
- `backend/external_docs/_how_to_add_sources.md`: 외부문서 추가 방법 문서이므로 git에 커밋합니다.
- `backend/external_docs/*.md`, `backend/external_docs/*.txt`: DART/뉴스 수집 결과이므로 git에 커밋하지 않습니다.

KOSDAQ 재무제표 분석 기능을 쓰려면 아래 명령으로 SQLite 캐시를 생성합니다.

```bash
cd backend
python scripts/import_financial_excel.py
```

## Local Run

```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

로컬 기본 주소는 다음과 같습니다.

- Frontend: `http://127.0.0.1:5173`
- Backend API: `http://127.0.0.1:8000`

배포 환경에서는 Render API 서비스에 LLM, DART, Naver News 환경변수를 설정합니다. 로컬에서 `.env`를 사용할 경우 민감한 키 파일은 git에 커밋하지 않습니다.

## Deploy

Notion 포트폴리오에서 면접관이 접속할 수 있게 하려면 공개 URL이 필요합니다. 이 저장소는 Render Blueprint(`render.yaml`)로 백엔드 API와 정적 프론트엔드를 함께 배포할 수 있게 구성되어 있습니다.

1. 이 저장소를 GitHub에 push합니다.
2. Render에서 New Blueprint를 선택하고 이 저장소를 연결합니다.
3. `corporate-finance-bot-api`와 `corporate-finance-bot-web` 두 서비스가 생성되는지 확인합니다.
4. API 서비스의 환경변수에 LLM/DART/뉴스 키를 입력합니다. 주가 조회는 네이버 금융 일별 종가를 우선 사용하고, 필요하면 Yahoo Finance를 보조로 사용하므로 별도 주가 API 키가 필요하지 않습니다.
5. 분석 실패 질문을 이메일로 수집하려면 API 서비스에 SMTP 환경변수를 설정합니다.
6. 배포가 끝나면 `corporate-finance-bot-web`의 `onrender.com` URL을 Notion에 연결합니다.

배포 구성은 다음 방식으로 동작합니다.

- API: `cd backend && uvicorn server:app --host 0.0.0.0 --port $PORT`
- Web: `frontend`에서 `npm ci && npm run build` 후 `dist`를 정적 사이트로 배포
- Web은 `VITE_API_HOSTNAME`으로 API 서비스의 Render 호스트명을 받아 `https://...` API를 호출합니다.
- API는 `BACKEND_CORS_ORIGIN_REGEX=https://.*\.onrender\.com` 설정으로 Render 정적 사이트의 요청을 허용합니다.
- `backend/data/financials.sqlite.gz`를 사용해 배포 환경에서 엑셀 전체 파싱 시간을 줄입니다.
- 분석 실패/데이터 부족 답변은 사용자 동의 팝업 후 `/api/feedback-email`로 질문과 답변을 전송할 수 있습니다. 이메일 발송에는 `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `FEEDBACK_EMAIL_TO`가 필요합니다. Gmail을 쓰는 경우 `SMTP_HOST`는 생략 가능하며 `SMTP_USERNAME`과 앱 비밀번호 형태의 `SMTP_PASSWORD`를 설정합니다.
- 이미지/PDF 첨부파일 문제 풀이는 비전 입력을 지원하는 LLM 설정이 필요합니다. Render API 서비스 환경변수에 `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-3.1-flash-lite`, `LLM_API_KEY` 또는 `GEMINI_API_KEY`를 설정합니다. OpenAI를 쓰는 경우 `LLM_PROVIDER=openai`, `LLM_MODEL`, `OPENAI_API_KEY` 또는 `LLM_API_KEY`를 설정합니다.

포트폴리오 공개용으로는 Render 무료 인스턴스를 사용할 수 있지만, 무료 인스턴스는 비활성 상태 후 첫 요청이 느릴 수 있습니다. 면접 직전에는 배포 URL을 한 번 열어 API가 깨어 있는지 확인하는 편이 좋습니다.

## Design

- RAG: `backend/knowledge/*.md`에서 재무관리 기준과 공식 설명을 검색합니다.
- External RAG: `backend/external_docs/`에 저장된 사업보고서와 뉴스 텍스트를 검색합니다.
- Tools: NPV, WACC, 재무비율, 운전자본, M&A, 기업 재무제표 조회, 추이 분석, 단순 전망, 주가 백테스팅을 Python으로 수행합니다.
- Charts: 재무 추이, 수익성 비율, 전망, 주가 종가 데이터를 프론트엔드 SVG 차트로 표시합니다.
- LLM: `backend/llm_client.py`에서 계산 결과와 검색 근거를 실무 답변 문장으로 정리합니다.
- File Questions: 프론트엔드에서 텍스트, PDF, 이미지 파일을 첨부해 문제 풀이를 요청할 수 있습니다. 텍스트 파일은 본문을 직접 전달하고, 이미지/PDF는 비전 입력을 지원하는 LLM 설정이 필요합니다.

## Development Direction

- 재무관리 이론 텍스트는 관련 `backend/knowledge/*.md` 파일에 정리합니다.
- 계산 가능한 공식과 예제는 대응되는 `backend/tools/*.py` 파일에 구현합니다.
- 새 주제가 기존 파일과 유사하면 기존 파일에 이어서 작성하고, 관련 파일이 없을 때만 새 파일을 만듭니다.
- 새 Tool을 추가하면 `backend/main_agent.py`, `backend/SKILL.md`, `README.md`에 함께 반영합니다.
- 답변은 RAG 검색 근거와 Python Tool 계산 결과를 조합해 생성합니다.
- 대용량 원본 데이터와 생성 캐시는 `.gitignore`에 추가하고, 재현 가능한 적재 스크립트와 매핑 규칙만 커밋합니다.
