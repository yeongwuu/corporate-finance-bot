# corporate-finance-bot

재무관리 질문을 처리하기 위한 RAG + LLM + Python 계산 Tool 기반 챗봇입니다.
재무관리 이론 질의, 계산형 문제, KOSDAQ 재무제표 기반 기업 분석, DART/뉴스 원문 기반 추이 분석을 지원합니다.

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
    ├── company_trend_tool.py      # 재무제표 추이와 외부문서 근거 기반 해석
    ├── mergers_acquisitions_tool.py # M&A 개념과 주요 계산
    ├── portfolio_tool.py          # 포트폴리오 기대수익률, 분산, 공분산 계산
    ├── risk_utility_tool.py       # 위험 태도, 기대효용, 전망이론, 보험료 계산
    ├── time_value_tool.py         # 화폐의 시간가치 계산
    ├── valuation_tool.py          # 배당할인모형과 주식가치 계산
    └── working_capital_tool.py    # 운전자본과 현금전환주기 계산
```

## Data

커밋용 재무제표 데이터는 용량을 줄이기 위해 2019~2025년의 재무상태표, 손익계산서, 현금흐름표만 포함합니다.

- `KOSDAQ_financial_statements.xlsx`: 커밋 대상 축소본입니다. 포함 시트는 `2019_BS`~`2025_CF`이며 자본변동표(`*_CE`)는 제외합니다. 파일 크기를 줄이기 위해 회사/시장/업종/계정/당기 금액 조회에 필요한 최소 컬럼만 유지합니다.
- `KOSDAQ_financial_statements.full.xlsx`: 로컬 전용 전체 원본 백업 파일입니다.
- `backend/data/financials.sqlite`: 엑셀에서 생성되는 로컬 캐시이며 git에 커밋하지 않습니다.
- `backend/data/account_mapping.json`: 주요 계정 추출 규칙이므로 git에 커밋합니다.
- `backend/external_docs/_how_to_add_sources.md`: 외부문서 추가 방법 문서이므로 git에 커밋합니다.
- `backend/external_docs/*.md`, `backend/external_docs/*.txt`: DART/뉴스 수집 결과이므로 git에 커밋하지 않습니다.

KOSDAQ 재무제표 분석 기능을 쓰려면 아래 명령으로 SQLite 캐시를 생성합니다.

```bash
cd backend
python scripts/import_financial_excel.py
```

## Backend Run

```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

선택적으로 `backend/.env`에 LLM, DART, 뉴스 API 키를 설정할 수 있습니다.

```text
LLM_PROVIDER=
LLM_MODEL=
LLM_API_KEY=
LLM_BASE_URL=
DART_API_KEY=
NEWS_PROVIDER=
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
```

## Frontend Run

```bash
cd frontend
npm install
npm run dev
```

기본 프론트엔드 주소는 `http://127.0.0.1:5173`이고, 백엔드는 `http://127.0.0.1:8000`에서 실행합니다.

## Design

- RAG: `backend/knowledge/*.md`에서 재무관리 기준과 공식 설명을 검색합니다.
- External RAG: `backend/external_docs/`에 저장된 사업보고서와 뉴스 텍스트를 검색합니다.
- Tools: NPV, WACC, 재무비율, 운전자본, M&A, 기업 재무제표 조회와 추이 분석을 Python으로 수행합니다.
- LLM: `backend/llm_client.py`에서 계산 결과와 검색 근거를 실무 답변 문장으로 정리합니다.

## Development Direction

- 재무관리 이론 텍스트는 관련 `backend/knowledge/*.md` 파일에 정리합니다.
- 계산 가능한 공식과 예제는 대응되는 `backend/tools/*.py` 파일에 구현합니다.
- 새 주제가 기존 파일과 유사하면 기존 파일에 이어서 작성하고, 관련 파일이 없을 때만 새 파일을 만듭니다.
- 새 Tool을 추가하면 `backend/main_agent.py`, `backend/SKILL.md`, `README.md`에 함께 반영합니다.
- 답변은 RAG 검색 근거와 Python Tool 계산 결과를 조합해 생성합니다.
- 대용량 원본 데이터와 생성 캐시는 `.gitignore`에 추가하고, 재현 가능한 적재 스크립트와 매핑 규칙만 커밋합니다.
