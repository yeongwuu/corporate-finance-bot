import React, { useMemo, useRef, useState } from "react";

const API_URL = import.meta.env?.VITE_API_URL || "http://localhost:8000";

const SAMPLE_PROMPTS = [
  "WACC와 APV 차이를 설명해줘",
  "M&A 시너지 효과 계산 방법을 설명해줘",
  "포이즌필 발효 후 지분율 계산 방법은?",
  "포트폴리오 기대수익률과 표준편차 계산 방법을 설명해줘",
];

const INITIAL_MESSAGE = {
  role: "assistant",
  content:
    "재무관리 질문을 입력하면 관련 이론을 검색하고 계산 도구를 선택해 답변합니다.",
  meta: {
    tool: "ready",
    status: "ok",
  },
};

export default function ChatUI() {
  const [messages, setMessages] = useState([INITIAL_MESSAGE]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [lastResult, setLastResult] = useState(null);
  const inputRef = useRef(null);

  const canSubmit = input.trim().length > 0 && !isLoading;

  const stats = useMemo(() => {
    const userCount = messages.filter((message) => message.role === "user").length;
    const assistantCount = messages.filter((message) => message.role === "assistant").length;
    return { userCount, assistantCount };
  }, [messages]);

  async function sendMessage(nextInput = input) {
    const question = nextInput.trim();
    if (!question || isLoading) return;

    const nextMessages = [
      ...messages,
      {
        role: "user",
        content: question,
      },
    ];

    setMessages(nextMessages);
    setInput("");
    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || "Request failed");
      }

      setLastResult(data);
      setMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: data.answer || "답변을 생성하지 못했습니다.",
          meta: {
            tool: data.tool,
            status: data.calculation?.status,
            references: data.references?.length || 0,
          },
        },
      ]);
    } catch (error) {
      setLastResult(null);
      setMessages([
        ...nextMessages,
        {
          role: "assistant",
          content:
            error.message === "Failed to fetch"
              ? "백엔드 서버에 연결하지 못했습니다."
              : error.message,
          meta: {
            tool: "network",
            status: "error",
          },
        },
      ]);
    } finally {
      setIsLoading(false);
      window.requestAnimationFrame(() => inputRef.current?.focus());
    }
  }

  function handlePromptClick(prompt) {
    setInput(prompt);
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Corporate Finance Bot</p>
          <h1>재무관리 챗봇</h1>
        </div>

        <div className="status-panel">
          <div>
            <span>API</span>
            <strong>{API_URL}</strong>
          </div>
          <div>
            <span>대화</span>
            <strong>{stats.userCount} / {stats.assistantCount}</strong>
          </div>
        </div>

        <nav className="topic-list" aria-label="지원 주제">
          <span>시간가치</span>
          <span>투자안 평가</span>
          <span>자본비용</span>
          <span>포트폴리오</span>
          <span>기업가치평가</span>
          <span>M&A</span>
        </nav>
      </aside>

      <section className="chat-panel" aria-label="채팅">
        <div className="message-list">
          {messages.map((message, index) => (
            <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
              <div className="message-header">
                <strong>{message.role === "user" ? "User" : "Assistant"}</strong>
                {message.meta?.tool ? <span>{message.meta.tool}</span> : null}
              </div>
              <p>{message.content}</p>
            </article>
          ))}

          {isLoading ? (
            <article className="message assistant loading">
              <div className="message-header">
                <strong>Assistant</strong>
                <span>working</span>
              </div>
              <p>답변을 생성하고 있습니다.</p>
            </article>
          ) : null}
        </div>

        <div className="prompt-row">
          {SAMPLE_PROMPTS.map((prompt) => (
            <button key={prompt} type="button" onClick={() => handlePromptClick(prompt)}>
              {prompt}
            </button>
          ))}
        </div>

        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            sendMessage();
          }}
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
              }
            }}
            placeholder="재무관리 질문을 입력하세요"
            rows={3}
          />
          <button type="submit" disabled={!canSubmit}>
            {isLoading ? "전송 중" : "전송"}
          </button>
        </form>
      </section>

      <aside className="inspector">
        <h2>응답 정보</h2>
        <dl>
          <div>
            <dt>도구</dt>
            <dd>{lastResult?.tool || "-"}</dd>
          </div>
          <div>
            <dt>상태</dt>
            <dd>{lastResult?.calculation?.status || "-"}</dd>
          </div>
          <div>
            <dt>근거</dt>
            <dd>{lastResult?.references?.length ?? 0}</dd>
          </div>
        </dl>

        <div className="reference-list">
          {(lastResult?.references || []).slice(0, 4).map((reference, index) => (
            <section key={`${reference.title}-${index}`}>
              <strong>{reference.title}</strong>
              <p>{reference.snippet}</p>
            </section>
          ))}
        </div>
      </aside>
    </main>
  );
}
