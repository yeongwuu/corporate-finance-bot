# Backend Skill Map

## RAG

- `rag/simple_rag.py`: `knowledge/*.md`에서 관련 재무관리 기준을 검색한다.
- 실무 배포 시 Chroma, FAISS, pgvector 같은 벡터DB로 교체할 수 있다.

## LLM

- `llm_client.py`: 계산 결과와 RAG 검색 결과를 최종 답변 문장으로 조립한다.
- 실제 LLM API는 이 파일의 `build_llm_prompt()` 위치에 연결한다.

## Tools

- `tools/capital_budgeting_tool.py`: NPV, 투자안 평가.
- `tools/cost_of_capital_tool.py`: WACC, 자본비용 계산.
- `tools/finance_concept_tool.py`: 재무관리 기초, FCF, 기업가치, 자본비용 개념 설명.
- `tools/financial_ratio_tool.py`: 유동비율, 부채비율, ROE 등 재무비율 계산.
- `tools/portfolio_tool.py`: 포트폴리오 기대수익률, 분산, 공분산, 상관계수 계산.
- `tools/risk_utility_tool.py`: 위험 태도, 기대효용, 확실성등가, 위험프리미엄 계산.
- `tools/time_value_tool.py`: 현재가치, 미래가치, 연금, 영구연금, 실효이자율 계산.
- `tools/valuation_tool.py`: 배당할인모형, 항상성장모형, NPVGO, PER, PBR 계산.
- `tools/working_capital_tool.py`: 운전자본과 현금전환주기 분석.
