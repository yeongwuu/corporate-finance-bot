# Development Summary

이 문서는 `corporate-finance-bot`의 백엔드, RAG/미들웨어, 프론트엔드, 데이터, 배포 구성을 구현 순서대로 요약합니다.

## 1. Backend API

- `backend/server.py`에 FastAPI 기반 API 서버를 구성했습니다.
- `/health` 엔드포인트로 배포/운영 상태를 확인할 수 있게 했습니다.
- `/api/chat` 엔드포인트가 사용자 질문을 받아 `main_agent`로 전달하고, 답변/사용 도구/계산 결과/RAG 근거를 JSON으로 반환합니다.
- `RequestValidationError` 핸들러를 추가해 잘못된 입력에 대해 일관된 422 응답을 제공합니다.
- 모든 요청에 처리 시간을 측정해 `X-Process-Time-Ms` 헤더로 내려주고, 요청 단위 로그를 남기도록 했습니다.
- 예외 발생 시 서버 내부 오류를 로깅하고 사용자에게는 한국어 오류 메시지를 반환합니다.

## 2. Backend Agent and Tool Routing

- `backend/main_agent.py`가 질문 내용을 기준으로 적절한 Tool을 선택합니다.
- 지원 범위는 재무관리 개념 설명, 시간가치, 투자안 평가, 자본비용, 재무비율, 운전자본, 포트폴리오, 위험/효용, 기업가치평가, M&A입니다.
- 기업명, 종목코드, 재무제표, 매출/영업이익/순이익/현금흐름 관련 질문은 기업 재무제표 분석 Tool로 라우팅합니다.
- 추이, 성장률, 원인, 뉴스, 사업보고서 관련 질문은 재무제표 추이 분석 Tool로 라우팅합니다.
- 각 Tool의 계산 결과와 RAG 검색 결과를 `backend/llm_client.py`로 전달해 최종 답변을 생성합니다.

## 3. Knowledge RAG

- `backend/rag/internal_rag.py`는 `backend/knowledge/*.md` 문서를 검색해 재무관리 이론 근거를 제공합니다.
- 지식 문서는 재무관리 정책, 기초 개념, 시간가치, 투자안 평가, 자본비용, 재무비율, 포트폴리오, 위험/수익, 운전자본, 기업가치평가, M&A, 답변 템플릿으로 나뉩니다.
- 계산형 질문도 단순 계산 결과만 반환하지 않고, 관련 이론 문서의 기준과 함께 답변하도록 구성했습니다.

## 4. Company Financial Statement Backend

- `KRX_financial_statements.xlsx`를 기반으로 코스피·코스닥 기업 재무제표 조회 기능을 구현했습니다.
- 커밋 가능한 크기를 위해 엑셀은 2019~2025년 `BS`, `PL`, `CF` 시트만 포함하고, 자본변동표 `CE`는 제외했습니다.
- 파일 크기를 줄이기 위해 조회에 필요한 최소 컬럼만 유지했습니다.
- `backend/company_data/financial_store.py`가 엑셀을 `backend/data/financials.sqlite` 캐시로 변환하고, 회사명/종목코드 검색과 연도별 계정 조회를 제공합니다.
- `backend/data/account_mapping.json`으로 매출액, 영업이익, 순이익, 자산, 부채, 자본, 현금흐름 등 주요 계정 매핑을 관리합니다.
- `backend/scripts/import_financial_excel.py`로 SQLite 캐시를 재생성할 수 있게 했습니다.

## 5. Company Analysis and Trend Tools

- `backend/tools/company_analysis_tool.py`는 특정 기업의 주요 재무계정과 기본 비율을 조회합니다.
- 계산 지표에는 매출 성장률, 영업이익률, 당기순이익률, 부채비율, 유동비율, 영업현금흐름/순이익 등이 포함됩니다.
- `backend/tools/company_trend_tool.py`는 여러 연도에 걸친 매출, 영업이익, 순이익, 현금흐름, 자산, 부채, 자본 추이를 분석합니다.
- 질문에 연도 범위가 없으면 가용 데이터 기준 최근 5개년을 기본값으로 사용합니다.
- 외부 문서 근거가 부족하면 재무제표 패턴 기반 해석과 추가 확인 방향을 구분해 답변합니다.

## 6. External RAG, DART, and News

- `backend/rag/external_rag.py`를 추가해 `backend/external_docs/`에 저장된 사업보고서/뉴스 텍스트를 검색합니다.
- `backend/dart_client.py`와 `backend/scripts/fetch_dart_report.py`로 DART 사업보고서 원문 수집을 지원합니다.
- `backend/news_client.py`와 `backend/scripts/fetch_news.py`로 네이버 뉴스 검색 결과 수집을 지원합니다.
- 기업 추이 분석 Tool은 질문 성격에 따라 저장된 외부 문서를 검색하고, 필요하면 DART/뉴스 API 키가 있을 때 자동 수집을 시도합니다.
- 생성된 외부 문서와 DART 캐시는 로컬 산출물로 보고 git에서 제외했습니다.

## 7. LLM Answer Layer

- `backend/llm_client.py`가 Tool 결과와 RAG 근거를 최종 답변 문장으로 정리합니다.
- `LLM_PROVIDER=openai` 또는 `LLM_PROVIDER=gemini` 설정을 통해 외부 LLM을 사용할 수 있습니다.
- API 키가 없거나 LLM 호출에 실패하면 rule-based 답변으로 fallback합니다.
- 답변 프롬프트는 숫자 변화, 원인 후보, 근거 문서, 추가 확인 사항을 분리해 설명하도록 설계했습니다.
- 투자 추천, 목표주가, 매수/매도 의견은 내지 않도록 제한했습니다.

## 8. Middleware and Runtime Configuration

- FastAPI 미들웨어에서 요청 처리 시간 측정, 요청 완료 로그, 예외 로깅을 처리합니다.
- CORS는 로컬 개발 주소를 기본 허용하고, 배포 환경에서는 환경변수로 조정할 수 있게 했습니다.
- `BACKEND_CORS_ORIGINS`는 쉼표로 구분된 명시적 origin 목록을 받습니다.
- `BACKEND_CORS_HOSTNAMES`는 hostname만 받아 `https://...` origin으로 변환합니다.
- `BACKEND_CORS_ORIGIN_REGEX`는 Render 등 배포 환경의 동적 서브도메인을 허용하는 데 사용합니다.

## 9. Frontend UI

- `frontend`에 Vite + React 기반 채팅 UI를 구성했습니다.
- `frontend/src/ChatUI.jsx`에서 사용자 질문을 입력받고 `/api/chat`으로 전송합니다.
- 응답 본문, 선택된 Tool, 계산 상태, 참고 근거 수, RAG 참고 문서를 UI에 표시합니다.
- 샘플 질문 버튼을 제공해 재무관리 주요 기능을 빠르게 테스트할 수 있게 했습니다.
- API 주소는 `VITE_API_URL` 또는 `VITE_API_HOSTNAME` 환경변수로 설정합니다.
- 로컬/LAN 테스트를 위해 Vite dev server는 `0.0.0.0`에 바인딩되도록 설정했습니다.

## 10. Local Data and Git Hygiene

- `.gitignore`에 `node_modules`, 프론트엔드 빌드 결과, Python 캐시, SQLite 캐시, DART/뉴스 생성물, 전체 원본 엑셀 백업을 제외했습니다.
- `KRX_financial_statements.xlsx` 축소본은 다른 사용자가 저장소만 받아도 기업 분석 기능을 실행할 수 있도록 커밋 대상에 포함합니다.
- `KRX_financial_statements.full.xlsx`는 로컬 백업 전용 원본이므로 커밋하지 않습니다.
- `backend/data/financials.sqlite`는 엑셀에서 재생성 가능한 캐시이므로 커밋하지 않습니다.

## 11. Deployment

- `render.yaml`을 추가해 Render에서 백엔드 API와 정적 프론트엔드를 함께 배포할 수 있게 했습니다.
- `corporate-finance-bot-api` 서비스는 Python 런타임으로 `uvicorn server:app --host 0.0.0.0 --port $PORT`를 실행합니다.
- `corporate-finance-bot-web` 서비스는 `frontend`를 빌드한 뒤 `dist`를 정적 사이트로 배포합니다.
- 프론트엔드는 Render의 API 서비스 hostname을 `VITE_API_HOSTNAME`으로 받아 배포된 API를 호출합니다.
- API는 `BACKEND_CORS_ORIGIN_REGEX=https://.*\.onrender\.com` 설정으로 Render 정적 사이트 요청을 허용합니다.
- 최종적으로 `corporate-finance-bot-web`의 공개 `onrender.com` URL을 Notion 포트폴리오에 연결하면 면접관이 챗봇에 접속할 수 있습니다.

## 12. Current Verification

- 축소 엑셀은 2019~2025년 `BS`, `PL`, `CF` 총 21개 시트로 구성되어 있습니다.
- `python scripts/import_financial_excel.py`로 SQLite 캐시 생성이 정상 동작함을 확인했습니다.
- `python -m py_compile`로 주요 백엔드 파일의 문법/임포트 검사를 통과했습니다.
- `npm run build`로 프론트엔드 production build가 정상 생성됨을 확인했습니다.
