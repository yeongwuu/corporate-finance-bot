# corporate-finance-bot

재무관리 질문을 처리하기 위한 RAG + LLM + Python 계산 Tool 기반 챗봇입니다.

## Structure

```text
frontend/
└── chat_ui.jsx                    # 사용자가 재무관리 질문을 입력하고 답변을 확인하는 채팅 UI

backend/
├── server.py                      # FastAPI 서버, 프론트엔드 요청을 받아 main_agent로 전달
├── main_agent.py                  # 질문 유형 판단, RAG 검색, Tool 실행을 조율하는 메인 라우터
├── llm_client.py                  # 계산 결과와 검색 근거를 최종 답변 문장으로 정리하는 LLM 연결 지점
├── requirements.txt               # 백엔드 실행에 필요한 Python 패키지 목록
├── SKILL.md                       # 백엔드 RAG, LLM, Tool 역할 요약
├── rag/
│   └── simple_rag.py              # knowledge 문서에서 질문과 관련된 기준을 검색하는 간단한 RAG
├── knowledge/
│   ├── corporate_finance_policy.md # 재무관리 답변과 계산의 기본 정책
│   ├── capital_budgeting.md        # NPV, IRR, 회수기간 등 투자안 평가 기준
│   ├── cost_of_capital.md          # WACC, CAPM, 할인율 관련 기준
│   ├── financial_ratios.md         # 유동비율, 부채비율, ROE 등 재무비율 기준
│   ├── working_capital.md          # 운전자본과 현금전환주기 기준
│   ├── valuation.md                # DCF, 기업가치, 배수평가 기준
│   └── report_templates.md         # 재무관리 답변 문장 템플릿
└── tools/
    ├── capital_budgeting_tool.py  # NPV와 투자안 평가 계산
    ├── cost_of_capital_tool.py    # WACC와 자본비용 계산
    ├── financial_ratio_tool.py    # 주요 재무비율 계산
    └── working_capital_tool.py    # 운전자본과 현금전환주기 계산
```

## Backend Run

```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

## Design

- RAG: `backend/knowledge/*.md`에서 재무관리 기준과 공식 설명을 검색합니다.
- Tools: NPV, WACC, 재무비율, 운전자본 계산을 Python으로 수행합니다.
- LLM: `backend/llm_client.py`에서 계산 결과와 검색 근거를 실무 답변 문장으로 정리합니다.
