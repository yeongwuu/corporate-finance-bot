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
- `tools/financial_ratio_tool.py`: 유동비율, 부채비율, ROE 등 재무비율 계산.
- `tools/working_capital_tool.py`: 운전자본과 현금전환주기 분석.
