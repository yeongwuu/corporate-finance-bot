import React, { useEffect, useMemo, useRef, useState } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

const API_HOSTNAME = import.meta.env?.VITE_API_HOSTNAME;
const API_URL =
  import.meta.env?.VITE_API_URL ||
  (API_HOSTNAME ? `https://${API_HOSTNAME}` : "http://localhost:8000");

const INITIAL_MESSAGE = {
  role: "assistant",
  content: "안녕하세요. 기업재무 챗봇입니다. 무엇이 궁금하세요?",
  meta: {
    tool: "ready",
    status: "ok",
  },
};

export default function ChatUI() {
  const [messages, setMessages] = useState([INITIAL_MESSAGE]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStartedAt, setLoadingStartedAt] = useState(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [lastResult, setLastResult] = useState(null);
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);

  const canSubmit = input.trim().length > 0 && !isLoading;

  const stats = useMemo(() => {
    const userCount = messages.filter((message) => message.role === "user").length;
    const assistantCount = messages.filter((message) => message.role === "assistant").length;
    return { userCount, assistantCount };
  }, [messages]);

  useEffect(() => {
    if (!isLoading || !loadingStartedAt) {
      setElapsedSeconds(0);
      return undefined;
    }

    const updateElapsed = () => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - loadingStartedAt) / 1000)));
    };

    updateElapsed();
    const timerId = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timerId);
  }, [isLoading, loadingStartedAt]);

  async function sendMessage(nextInput = input) {
    const question = nextInput.trim();
    if (!question || isLoading) return;
    const history = buildConversationHistory(messages);

    const nextMessages = [
      ...messages,
      {
        role: "user",
        content: question,
      },
    ];

    setMessages(nextMessages);
    setInput("");
    setLoadingStartedAt(Date.now());
    setIsLoading(true);
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history }),
        signal: abortController.signal,
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
            animate: true,
            tool: data.tool,
            status: data.calculation?.status,
            references: data.references?.length || 0,
            chart: data.chart,
            trace: data.trace || [],
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
            error.name === "AbortError"
              ? "요청을 취소했습니다."
              : error.message === "Failed to fetch"
                ? "백엔드 서버에 연결하지 못했습니다."
                : error.message,
          meta: {
            animate: true,
            tool: error.name === "AbortError" ? "cancelled" : "network",
            status: error.name === "AbortError" ? "cancelled" : "error",
          },
        },
      ]);
    } finally {
      abortControllerRef.current = null;
      setIsLoading(false);
      setLoadingStartedAt(null);
      window.requestAnimationFrame(() => inputRef.current?.focus());
    }
  }

  function cancelMessage() {
    abortControllerRef.current?.abort();
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Corporate Finance Bot</p>
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

      </aside>

      <section className="chat-panel" aria-label="채팅">
        <div className="message-list">
          {messages.map((message, index) => (
            <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
              <div className="message-header">
                <strong>{message.role === "user" ? "User" : "Assistant"}</strong>
              </div>
              <MessageText message={message} />
            </article>
          ))}

          {isLoading ? (
            <article className="message assistant loading">
              <div className="message-header">
                <strong>Assistant</strong>
                <span className="loading-status">
                  <span aria-hidden="true" className="hourglass">⌛</span>
                  <span>{elapsedSeconds}s</span>
                  <span>working</span>
                </span>
              </div>
              <p>답변을 생성하고 있습니다.</p>
            </article>
          ) : null}
        </div>

        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            if (isLoading) {
              cancelMessage();
              return;
            }
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
                if (isLoading) return;
                sendMessage();
              }
            }}
            placeholder="이곳에 질문을 입력하세요!"
            rows={3}
          />
          <button
            type={isLoading ? "button" : "submit"}
            className={isLoading ? "cancel-button" : undefined}
            disabled={!isLoading && !canSubmit}
            onClick={isLoading ? cancelMessage : undefined}
          >
            {isLoading ? "취소" : "전송"}
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
          <div>
            <dt>뉴스</dt>
            <dd>{formatNewsStatus(lastResult?.calculation)}</dd>
          </div>
        </dl>

        <ChartPanel chart={lastResult?.chart} />

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

function MessageText({ message }) {
  const [visibleText, setVisibleText] = useState(message.meta?.animate ? "" : message.content);
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [isFolded, setIsFolded] = useState(false);
  const [showTrace, setShowTrace] = useState(false);
  const isInitialAssistantMessage = message.role === "assistant" && message.meta?.tool === "ready";
  const trace = message.meta?.trace || [];

  useEffect(() => {
    if (!message.meta?.animate) {
      setVisibleText(message.content);
      return undefined;
    }

    setVisibleText("");
    let index = 0;
    const step = Math.max(2, Math.min(10, Math.floor(message.content.length / 180)));
    const timerId = window.setInterval(() => {
      index = Math.min(message.content.length, index + step);
      setVisibleText(message.content.slice(0, index));
      if (index >= message.content.length) {
        window.clearInterval(timerId);
      }
    }, 16);

    return () => window.clearInterval(timerId);
  }, [message.content, message.meta?.animate]);

  if (message.role === "user") {
    return <p>{visibleText}</p>;
  }

  async function copyMessage() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  return (
    <>
      {isFolded ? (
        <p className="message-preview">{buildPreview(message.content)}</p>
      ) : (
        <>
          <div className="message-body">{formatAnswerText(visibleText)}</div>
          <ChartPanel chart={message.meta?.chart} compact />
          {trace.length > 0 ? <TracePanel trace={trace} isOpen={showTrace} /> : null}
        </>
      )}
      {!isInitialAssistantMessage ? (
        <div className="message-actions" aria-label="답변 작업">
          {trace.length > 0 ? (
            <button
              type="button"
              onClick={() => setShowTrace(!showTrace)}
              aria-label={showTrace ? "처리 과정 숨기기" : "처리 과정 보기"}
              title={showTrace ? "처리 과정 숨기기" : "처리 과정 보기"}
            >
              과정
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => setIsFolded(!isFolded)}
            aria-label={isFolded ? "답변 펼치기" : "답변 접기"}
            title={isFolded ? "답변 펼치기" : "답변 접기"}
          >
            {isFolded ? "펼치기" : "접기"}
          </button>
          <button type="button" onClick={copyMessage} aria-label="답변 복사" title="답변 복사">
            {copied ? "Copied" : "Copy"}
          </button>
          <button
            type="button"
            className={feedback === "up" ? "active" : undefined}
            onClick={() => setFeedback(feedback === "up" ? null : "up")}
            aria-label="좋아요"
            title="좋아요"
          >
            👍
          </button>
          <button
            type="button"
            className={feedback === "down" ? "active" : undefined}
            onClick={() => setFeedback(feedback === "down" ? null : "down")}
            aria-label="비추천"
            title="비추천"
          >
            👎
          </button>
        </div>
      ) : null}
    </>
  );
}

function TracePanel({ trace, isOpen }) {
  if (!isOpen) return null;
  return (
    <div className="trace-panel" aria-label="백엔드 처리 과정">
      <strong>처리 과정</strong>
      <ol>
        {trace.map((item, index) => (
          <li key={`${item.label}-${index}`}>
            <span>{item.label}</span>
            <p>{item.detail}</p>
            <em>{item.elapsed_ms}ms</em>
          </li>
        ))}
      </ol>
    </div>
  );
}

function buildConversationHistory(messages) {
  return messages
    .filter((message) => message.role === "user" || message.role === "assistant")
    .filter((message) => message.content !== INITIAL_MESSAGE.content)
    .slice(-6)
    .map((message) => ({
      role: message.role,
      content: message.content.slice(0, 900),
    }));
}

function buildPreview(content) {
  const compact = content.replace(/\s+/g, " ").trim();
  if (!compact) return "접힌 답변입니다.";
  return compact.length > 120 ? `${compact.slice(0, 120)}...` : compact;
}

function formatAnswerText(text) {
  if (!text) return null;

  return text.split(/\n{2,}/).map((block, blockIndex) => {
    const lines = block.split("\n").map(cleanDisplayLine).filter((line) => line && !isDecorativeIconLine(line));
    if (lines.length === 1) {
      return renderAnswerLine(lines[0], `${blockIndex}-0`);
    }
    return (
      <div className="answer-block" key={blockIndex}>
        {lines.map((line, lineIndex) => renderAnswerLine(line, `${blockIndex}-${lineIndex}`))}
      </div>
    );
  });
}

function isDecorativeIconLine(line) {
  return /^[\p{Emoji_Presentation}\p{Extended_Pictographic}\s]+$/u.test(line.trim());
}

function renderAnswerLine(line, key) {
  const heading = getHeadingMeta(line);
  if (heading) {
    return (
      <p className="answer-heading" key={key}>
        <span aria-hidden="true">{heading.icon}</span>
        <strong>{renderInlineMath(heading.text)}</strong>
      </p>
    );
  }
  return <p key={key}>{renderInlineMath(line)}</p>;
}

function getHeadingMeta(line) {
  const trimmed = line.trim();
  const plain = trimmed
    .replace(/^#{1,6}\s*/, "")
    .replace(/^\d+[.)]\s*/, "")
    .replace(/[:：]\s*$/, "")
    .trim();
  const isHeadingShape =
    /^#{1,6}\s+/.test(trimmed) ||
    /^\d+[.)]\s+/.test(trimmed) ||
    (plain.length <= 24 && /[:：]$/.test(trimmed));
  const headingRules = [
    { tokens: ["핵심 요약", "요약"], icon: "✨" },
    { tokens: ["비교 대상"], icon: "⚖️" },
    { tokens: ["연도별 추이", "숫자 추이"], icon: "📈" },
    { tokens: ["인사이트"], icon: "💡" },
    { tokens: ["원인", "배경"], icon: "🔎" },
    { tokens: ["뉴스", "시장 반응"], icon: "📰" },
    { tokens: ["계산 요약"], icon: "🧮" },
    { tokens: ["기간:"], icon: "🏢" },
  ];
  const rule = headingRules.find((candidate) => candidate.tokens.some((token) => plain.includes(token)));
  if (!rule || !isHeadingShape) return null;
  return { ...rule, text: plain };
}

function cleanDisplayLine(line) {
  return line
    .replace(/^#{1,6}\s*/, "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__(.*?)__/g, "$1")
    .replace(/^\s*[*-]\s+/, "- ")
    .trim();
}

function renderInlineMath(text) {
  const parts = splitMathSegments(text);
  return parts.map((part, index) => {
    if (!part.math) return <React.Fragment key={index}>{part.value}</React.Fragment>;
    return <MathFormula key={index} expression={part.value} displayMode={part.displayMode} />;
  });
}

function splitMathSegments(text) {
  const segments = [];
  const pattern = /(\$\$[^$]+\$\$|\$[^$\n]+\$|\\\([^)]*\\\)|\\\[[\s\S]*?\\\])/g;
  let lastIndex = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > lastIndex) {
      segments.push({ math: false, value: text.slice(lastIndex, match.index) });
    }
    const token = match[0];
    const displayMode = token.startsWith("$$") || token.startsWith("\\[");
    segments.push({ math: true, displayMode, value: unwrapMathToken(token) });
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) {
    segments.push({ math: false, value: text.slice(lastIndex) });
  }
  return segments;
}

function unwrapMathToken(token) {
  if (token.startsWith("$$")) return token.slice(2, -2).trim();
  if (token.startsWith("$")) return token.slice(1, -1).trim();
  if (token.startsWith("\\(")) return token.slice(2, -2).trim();
  if (token.startsWith("\\[")) return token.slice(2, -2).trim();
  return token;
}

function MathFormula({ expression, displayMode }) {
  try {
    const html = katex.renderToString(expression, {
      displayMode,
      throwOnError: false,
      strict: false,
    });
    const className = displayMode ? "math-formula display" : "math-formula";
    return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />;
  } catch {
    return <code className="math-fallback">{expression}</code>;
  }
}

function formatNewsStatus(calculation) {
  const newsFetch = calculation?.news_fetch;
  const externalCount = calculation?.external_references?.length || 0;
  if (newsFetch?.status === "ok") return `수집 ${newsFetch.count ?? externalCount}건`;
  if (newsFetch?.status) return "미수집";
  if (externalCount > 0) return `외부근거 ${externalCount}건`;
  return "-";
}

function ChartPanel({ chart, compact = false }) {
  if (!chart) return null;
  return (
    <section className={`chart-card${compact ? " compact" : ""}`}>
      <div className="chart-title">
        <strong>{chart.title}</strong>
        {chart.subtitle ? <span>{chart.subtitle}</span> : null}
      </div>
      {chart.type === "line" ? <LineChart chart={chart} /> : null}
      {chart.type === "bar" ? <BarChart chart={chart} /> : null}
      {chart.range ? (
        <div className="forecast-range" aria-label="전망 범위">
          <span>보수 {chart.range.low}</span>
          <span>기준 {chart.range.base}</span>
          <span>낙관 {chart.range.high}</span>
        </div>
      ) : null}
    </section>
  );
}

function LineChart({ chart }) {
  const width = 420;
  const height = 240;
  const padding = { top: 18, right: 24, bottom: 34, left: 72 };
  const allPoints = chart.datasets.flatMap((dataset) => dataset.points);
  const xValues = allPoints.map((point) => point.x);
  const yValues = allPoints.map((point) => point.y);
  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const rawMinY = Math.min(...yValues);
  const rawMaxY = Math.max(...yValues);
  const paddingY = Math.max((rawMaxY - rawMinY) * 0.12, Math.abs(rawMaxY) * 0.03, 1);
  const minY = rawMinY >= 0 ? Math.max(0, rawMinY - paddingY) : rawMinY - paddingY;
  const maxY = rawMaxY + paddingY;
  const yRange = maxY - minY || 1;
  const xRange = maxX - minX || 1;
  const yTicks = [0, 0.5, 1].map((ratio) => minY + yRange * ratio);
  const xTicks = buildXTicks(allPoints);

  const scaleX = (value) => padding.left + ((value - minX) / xRange) * (width - padding.left - padding.right);
  const scaleY = (value) => height - padding.bottom - ((value - minY) / yRange) * (height - padding.top - padding.bottom);

  return (
    <div className="line-chart">
      <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={chart.title}>
        {yTicks.map((tick) => (
          <g key={tick}>
            <line className="chart-grid" x1={padding.left} y1={scaleY(tick)} x2={width - padding.right} y2={scaleY(tick)} />
            <text x={padding.left - 8} y={scaleY(tick) + 3} textAnchor="end">{formatChartValue(tick, chart.unit)}</text>
          </g>
        ))}
        <line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} />
        <line x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} />
        {chart.datasets.map((dataset, index) => {
          const path = dataset.points
            .map((point, pointIndex) => `${pointIndex === 0 ? "M" : "L"} ${scaleX(point.x)} ${scaleY(point.y)}`)
            .join(" ");
          return (
            <g key={dataset.key}>
              <path className={`chart-line line-${index % 4}${dataset.forecast ? " forecast" : ""}`} d={path} />
              {dataset.points.map((point) => (
                <circle
                  key={`${dataset.key}-${point.x}`}
                  className={point.forecast ? "forecast-point" : undefined}
                  cx={scaleX(point.x)}
                  cy={scaleY(point.y)}
                  r={point.forecast ? "4.5" : "3.4"}
                >
                  <title>{`${dataset.label} ${point.label}: ${point.display}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
        {xTicks.map((tick) => (
          <text key={`${tick.x}-${tick.label}`} x={scaleX(tick.x)} y={height - 10} textAnchor="middle">{tick.label}</text>
        ))}
      </svg>
      <div className="chart-legend">
        {chart.datasets.map((dataset, index) => (
          <span key={dataset.key}>
            <i className={`legend-swatch line-${index % 4}`} />
            {dataset.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function buildXTicks(points) {
  const unique = [];
  const seen = new Set();
  for (const point of points) {
    if (seen.has(point.x)) continue;
    seen.add(point.x);
    unique.push({ x: point.x, label: point.label || String(point.x) });
  }
  unique.sort((a, b) => a.x - b.x);
  if (unique.length <= 7) return unique;
  const middle = unique[Math.floor(unique.length / 2)];
  return [unique[0], middle, unique[unique.length - 1]];
}

function formatChartValue(value, unit) {
  if (unit === "PERCENT") return `${value.toFixed(1)}%`;
  if (unit === "KRW_PRICE") return `${Math.round(value).toLocaleString("ko-KR")}원`;
  const abs = Math.abs(value);
  if (abs >= 1_0000_0000_0000) return `${(value / 1_0000_0000_0000).toFixed(0)}조`;
  if (abs >= 1_0000_0000) return `${(value / 1_0000_0000).toFixed(0)}억`;
  if (abs >= 10_000) return `${(value / 10_000).toFixed(0)}만`;
  return value.toFixed(0);
}

function BarChart({ chart }) {
  const maxValue = Math.max(...chart.bars.map((bar) => Math.abs(bar.value)), 1);
  return (
    <div className="bar-chart">
      {chart.bars.map((bar) => (
        <div className="bar-row" key={bar.key}>
          <span>{bar.label}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${Math.max(4, (Math.abs(bar.value) / maxValue) * 100)}%` }} />
          </div>
          <strong>{bar.display}</strong>
        </div>
      ))}
    </div>
  );
}
