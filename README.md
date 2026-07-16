# Corporate Finance Bot

기업재무 이론, 계산 문제, 상장기업 재무제표, 산업 비교, 뉴스·공시, 주가 분석을 하나의 대화형 인터페이스에서 처리하는 AI 재무 분석 챗봇입니다.

- 배포 URL: https://corporate-finance-bot-web.onrender.com
- Backend: FastAPI + Uvicorn (API 접수, 입력 검증, SSE 진행 상태, 오류 처리)
- Frontend: React + Vite
- Data: SQLite, DART Open API, Naver News, Naver Finance, Yahoo Finance
- LLM: Gemini 또는 OpenAI

FastAPI는 분석 계산을 직접 수행하는 엔진이 아니라 React 화면과 Main Agent를 연결하는 API 관문입니다. 질문을 검증해 분석 경로로 전달하고, Python Tool·RAG·SQLite·외부 API가 만든 결과를 실시간으로 반환합니다.

## 주요 기능

- 기업명·종목코드 기반 주요 재무계정 및 연도별 추이 조회
- 매출총이익률, 영업이익률, 당기순이익률, 자기자본이익률, 총자산이익률, 투하자본수익률 등 재무비율 계산
- CAGR, 선형추세, 가중 성장률을 이용한 단순 재무 전망
- 대표 산업·섹터 기업 선정과 매출·영업이익 비교
- NPV, IRR, WACC, 포트폴리오, M&A, 운전자본 등 재무관리 계산
- WACC·영구성장률별 DCF 민감도와 현재 주가 대비 고평가·저평가 비교
- 금리·환율·반도체 가격 복합 스트레스, 매출·원가율 및 배당성장률 변화 시나리오 분석
- 주가 수익률, 변동성, MDD 및 Random Forest 기반 실험적 예측
- DART·뉴스가 필요한 질문에만 외부 근거 적용
- 텍스트·PDF·이미지 첨부 문제 풀이

## 대화 및 추천 UX

- 회사명이 필요한 질문은 이전 회사를 임의로 상속하지 않고 기업명을 먼저 확인합니다.
- 사용자가 기업명만 후속 입력하면 직전 미완성 질문과 연결해 분석합니다.
- 기업 선택 단계에서는 삼성전자와 재무 DB의 무작위 기업 2개를 예시로 제공합니다.
- 추천 질문 풀은 재무 DB의 기업·산업군과 가치평가·스트레스 시나리오를 조합한 고유 질문 200개로 구성됩니다.
- 오른쪽 추천 패널은 대화 중에도 유지되며 직전 추천 5개는 다음 재생성에서 제외됩니다.

## 답변과 차트

- 계산은 Python Tool이 수행하고 LLM은 결과와 근거를 자연어로 정리합니다.
- 수익성 지표명은 매출총이익률, 영업이익률, 당기순이익률, 자기자본이익률, 총자산이익률, 투하자본수익률로 통일합니다.
- 재무 데이터만으로 답할 수 있는 질문에는 뉴스 출처를 표시하지 않습니다.
- 재무 추이, 비율, 전망, 주가를 SVG 차트로 표시합니다.
- 규모가 크게 다른 복수 재무계정은 첫해를 100으로 환산해 추이를 비교합니다.
- 복수 범례 차트는 각 데이터 시리즈의 최댓값을 마커로 표시합니다.
- 답변 접기, 복사, 좋아요·비추천, 실시간 처리 단계 표시를 지원합니다.

## 실패 질문 수집과 개인정보 동의

실패 질문은 자동으로 수집하지 않습니다.

- 데이터 부족이나 분석 실패 답변 아래에 수집 동의 영역을 표시합니다.
- 사용자가 체크박스를 선택하고 `동의` 버튼을 눌렀을 때만 `backend/data/failed_questions.json`에 기록합니다.
- `비동의`를 누르거나 아무 선택도 하지 않으면 저장하지 않습니다.
- 이메일·SMTP 전송 기능은 사용하지 않습니다.

## 처리 구조

```text
React ChatUI
    ↓  POST /api/chat (SSE)
FastAPI server
    ↓
main_agent.py
    ├── Internal RAG: backend/knowledge/*.md
    ├── External RAG: DART / Naver News
    ├── Financial DB: Excel → SQLite
    └── Python Tools
            ↓
LLM answer + chart_builder.py
            ↓
Text / formula / source / SVG chart
```

Internal RAG는 `backend/knowledge/`의 9개 재무관리 기준 문서에서 공식과 개념을 찾습니다. External RAG는 DART 사업보고서와 네이버 뉴스에서 기업·산업의 최신 사실을 찾습니다. 공식은 내부 지식, 최신 실적 원인은 외부 자료처럼 역할을 분리하며, 질문에 따라 두 경로를 함께 사용합니다.

## 프로젝트 구조

```text
frontend/
├── src/ChatUI.jsx          # 채팅, 추천 질문, 동의 UI, 차트 렌더링
├── src/styles.css          # 반응형 UI 스타일
└── src/main.jsx            # React 진입점

backend/
├── server.py               # FastAPI, SSE, 추천 질문, 동의 기반 실패 로그
├── main_agent.py           # 질문 분류, 맥락 연결, Tool 조율
├── llm_client.py           # LLM 및 규칙 기반 답변 생성
├── chart_builder.py        # 차트 데이터 스펙 생성
├── dart_client.py          # DART 공시·재무계정 조회
├── news_client.py          # Naver News 수집
├── company_data/
│   └── financial_store.py  # SQLite 재무 데이터 조회
├── data/
│   ├── account_mapping.json
│   ├── financials.sqlite.gz
│   └── successful_questions.json
├── rag/
│   ├── internal_rag.py
│   └── external_rag.py
├── knowledge/              # 재무관리 기준 문서 9개
└── tools/                  # 재무 분석·계산 Tool
```

## 데이터

재무 데이터는 2019~2025년 재무상태표, 손익계산서, 현금흐름표를 포함합니다. 파일명은 기존 호환성을 위해 `KOSDAQ_financial_statements.xlsx`를 유지하지만 SQLite에는 유가증권시장, 코스닥시장 및 일부 기타법인 데이터가 포함됩니다.

- `KOSDAQ_financial_statements.xlsx`: 커밋용 축소 원본
- `KOSDAQ_financial_statements.full.xlsx`: 로컬 전체 원본 백업
- `backend/data/financials.sqlite`: 로컬 조회 캐시
- `backend/data/financials.sqlite.gz`: Render 배포용 압축 캐시
- `backend/data/account_mapping.json`: 표준 재무계정 매핑
- `backend/data/successful_questions.json`: 추천 질문 200개 풀

SQLite 캐시 재생성:

```bash
cd backend
python scripts/import_financial_excel.py
```

## API

| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/health` | 서버 상태 확인 |
| `GET` | `/api/recommended-questions` | 추천 질문 5개와 전체 풀 크기 반환 |
| `POST` | `/api/chat` | SSE 방식 질문 처리 |
| `POST` | `/api/failed-question-log` | 명시적 동의가 있는 실패 질문만 기록 |

`/api/trending-questions`는 이전 프론트엔드 호환을 위한 추천 질문 별칭입니다.

## 로컬 실행

Backend:

```bash
pip install -r backend/requirements.txt
cd backend
uvicorn server:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

- Frontend: http://127.0.0.1:5173
- Backend: http://127.0.0.1:8000

## 환경변수

LLM 사용 시 `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`를 설정합니다. 공급자별 키인 `GEMINI_API_KEY` 또는 `OPENAI_API_KEY`도 사용할 수 있으며, 별도 API 주소가 필요하면 `LLM_BASE_URL`을 추가합니다.

DART 공시 조회에는 `DART_API_KEY`, 네이버 뉴스 조회에는 `NAVER_CLIENT_ID`와 `NAVER_CLIENT_SECRET`을 사용합니다. `NEWS_PROVIDER`의 기본값은 `naver`입니다.

로컬·배포 환경의 연결 설정은 백엔드의 `BACKEND_CORS_ORIGINS`, `BACKEND_CORS_HOSTNAMES`, `BACKEND_CORS_ORIGIN_REGEX`와 프론트엔드의 `VITE_API_URL`, `VITE_API_HOSTNAME`으로 지정합니다. 주가 캐시 시간과 DART 요청 제한은 필요할 때 `PRICE_CACHE_TTL_SECONDS`, `DART_HTTP_TIMEOUT_SECONDS`로 조정할 수 있습니다.

민감한 키와 `.env` 파일은 커밋하지 않습니다.

## 배포

`render.yaml`은 API와 정적 웹 서비스를 함께 배포합니다.

1. 저장소를 GitHub에 push합니다.
2. Render에서 Blueprint로 저장소를 연결합니다.
3. API 서비스에 LLM, DART, Naver 환경변수를 설정합니다.
4. `corporate-finance-bot-api`와 `corporate-finance-bot-web`을 배포합니다.

배포 명령:

- API: `cd backend && uvicorn server:app --host 0.0.0.0 --port $PORT`
- Web: `npm ci && npm run build`

Render 무료 인스턴스는 비활성화 후 첫 요청이 느릴 수 있습니다.

## 개발 원칙

- 이론과 공식은 `backend/knowledge/`에 관리합니다.
- 결정적 계산은 `backend/tools/`의 Python 코드로 처리합니다.
- LLM은 계산 결과와 검색 근거를 설명하는 역할로 제한합니다.
- 뉴스·공시는 질문 의도상 필요한 경우에만 조회합니다.
- 오류가 발생하면 판단한 원인과 로그를 바탕으로 해결안을 비교하고 영향 범위를 검토한 뒤 적용합니다.
- 새 Tool을 추가하면 `main_agent.py`, `backend/SKILL.md`, README를 함께 갱신합니다.
