import React, { useState } from "react";

const API_URL = import.meta.env?.VITE_API_URL || "http://localhost:8000";

export default function ChatUI() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function sendMessage() {
    const question = input.trim();
    if (!question || isLoading) return;

    const nextMessages = [...messages, { role: "user", content: question }];
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
      setMessages([
        ...nextMessages,
        { role: "assistant", content: data.answer || "답변을 생성하지 못했습니다." },
      ]);
    } catch {
      setMessages([
        ...nextMessages,
        { role: "assistant", content: "백엔드 서버에 연결하지 못했습니다." },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="chat-shell">
      <section className="message-list">
        {messages.map((message, index) => (
          <article key={index} className={`message message-${message.role}`}>
            {message.content}
          </article>
        ))}
      </section>

      <form
        className="chat-input"
        onSubmit={(event) => {
          event.preventDefault();
          sendMessage();
        }}
      >
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="재무관리 질문을 입력하세요"
          rows={3}
        />
        <button type="submit" disabled={isLoading || !input.trim()}>
          전송
        </button>
      </form>
    </main>
  );
}
