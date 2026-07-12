import React, { useEffect, useRef, useState } from "react";
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
  const [attachedFile, setAttachedFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStartedAt, setLoadingStartedAt] = useState(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [activeStep, setActiveStep] = useState(0);
  const [pendingFeedback, setPendingFeedback] = useState(null);
  const [feedbackNotice, setFeedbackNotice] = useState("");
  const [isSendingFeedback, setIsSendingFeedback] = useState(false);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);
  const abortControllerRef = useRef(null);

  const canSubmit = (input.trim().length > 0 || Boolean(attachedFile)) && !isLoading;

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

  useEffect(() => {
    if (!feedbackNotice) return undefined;
    const timerId = window.setTimeout(() => setFeedbackNotice(""), 5000);
    return () => window.clearTimeout(timerId);
  }, [feedbackNotice]);

  async function sendMessage(nextInput = input) {
    const question = nextInput.trim();
    if ((!question && !attachedFile) || isLoading) return;
    const history = buildConversationHistory(messages);
    const displayQuestion = question || "첨부파일의 문제를 풀어줘";
    let attachment = null;
    try {
      attachment = attachedFile ? await readAttachment(attachedFile) : null;
    } catch (error) {
      setFeedbackNotice(error.message || "파일을 읽지 못했습니다.");
      return;
    }

    const nextMessages = [
      ...messages,
      {
        role: "user",
        content: attachment ? `${displayQuestion}\n\n첨부파일: ${attachment.name}` : displayQuestion,
      },
    ];

    setMessages(nextMessages);
    setInput("");
    setAttachedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    setLoadingStartedAt(Date.now());
    setActiveStep(0);
    setIsLoading(true);
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: displayQuestion, history, attachment }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error("Request failed");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let data = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = null;

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;

          if (trimmed.startsWith("event:")) {
            currentEvent = trimmed.replace("event:", "").trim();
          } else if (trimmed.startsWith("data:")) {
            const rawData = trimmed.replace("data:", "").trim();
            try {
              const parsed = JSON.parse(rawData);
              if (currentEvent === "step") {
                setActiveStep(parsed.step_index);
              } else if (currentEvent === "result") {
                data = parsed;
              } else if (currentEvent === "error") {
                throw new Error(parsed.message || "Execution error");
              }
            } catch (err) {
              console.error("Failed to parse event stream chunk", err);
            }
          }
        }
      }

      if (!data) {
        throw new Error("답변 데이터를 수신하지 못했습니다.");
      }

      const answer = data.answer || "답변을 생성하지 못했습니다.";
      setMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: answer,
          meta: {
            animate: true,
            tool: data.tool,
            status: data.calculation?.status,
            references: buildDisplayReferences(data.references),
            chart: data.chart,
            trace: data.trace || [],
            suggestions: shouldShowAlternativeQuestions(answer, data)
              ? buildAlternativeQuestions(displayQuestion)
              : [],
          },
        },
      ]);
      if (shouldAskFeedbackConsent(data, answer)) {
        setPendingFeedback({
          question: displayQuestion,
          attachmentName: attachment?.name,
          answer,
          tool: data.tool,
          status: data.calculation?.status,
        });
      }
    } catch (error) {
      const answer =
        error.name === "AbortError"
          ? "요청을 취소했습니다."
          : error.message === "Failed to fetch"
            ? "백엔드 서버에 연결하지 못했습니다."
            : error.message;
      setMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: answer,
          meta: {
            animate: true,
            tool: error.name === "AbortError" ? "cancelled" : "network",
            status: error.name === "AbortError" ? "cancelled" : "error",
            suggestions: error.name === "AbortError" ? [] : buildAlternativeQuestions(displayQuestion),
          },
        },
      ]);
      if (error.name !== "AbortError") {
        setPendingFeedback({
          question: displayQuestion,
          attachmentName: attachment?.name,
          answer,
          tool: "network",
          status: "error",
        });
      }
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

  async function submitFeedbackEmail() {
    if (!pendingFeedback || isSendingFeedback) return;
    setIsSendingFeedback(true);
    setFeedbackNotice("");
    try {
      const response = await fetch(`${API_URL}/api/feedback-email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...pendingFeedback, consent: true }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || "이메일 전송에 실패했습니다.");
      }
      setFeedbackNotice(data.message || "질문과 답변 내용을 전송했습니다.");
      setPendingFeedback(null);
    } catch (error) {
      setFeedbackNotice(error.message || "이메일 전송에 실패했습니다.");
      setPendingFeedback(null);
    } finally {
      setIsSendingFeedback(false);
    }
  }

  function dismissFeedbackEmail() {
    setPendingFeedback(null);
    setFeedbackNotice("수집하지 않고 닫았습니다.");
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Corporate Finance Bot</p>
        </div>
      </aside>

      <section className="chat-panel" aria-label="채팅">
        <div className="message-list">
          {messages.map((message, index) => (
            <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
              <div className="message-header">
                <strong>{message.role === "user" ? "User" : "Assistant"}</strong>
              </div>
              <MessageText message={message} onAskSuggestion={sendMessage} />
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
              <p>질문을 분석하고 필요한 데이터를 조회하는 중입니다.</p>
              <LoadingTrace activeStep={activeStep} />
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
          {attachedFile ? (
            <div className="attachment-chip">
              <span>{attachedFile.name}</span>
              <button type="button" onClick={() => setAttachedFile(null)} aria-label="첨부파일 제거">
                삭제
              </button>
            </div>
          ) : null}
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
          <input
            ref={fileInputRef}
            type="file"
            className="file-input"
            accept=".txt,.md,.csv,.json,.pdf,image/*"
            onChange={(event) => setAttachedFile(event.target.files?.[0] || null)}
          />
          <button
            type="button"
            className="attach-button"
            data-tooltip="문제를 업로드하세요!"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
          >
            파일
          </button>
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

      {feedbackNotice ? (
        <div className="feedback-toast" role="status">
          {feedbackNotice}
        </div>
      ) : null}
      {pendingFeedback ? (
        <div className="consent-backdrop" role="presentation">
          <section className="consent-dialog" role="dialog" aria-modal="true" aria-labelledby="feedback-consent-title">
            <h2 id="feedback-consent-title">답변 개선을 위해 내용을 전송할까요?</h2>
            <p>
              이 질문은 챗봇이 충분히 분석하지 못한 것으로 보입니다. 질문과 답변 내용을 개발자 이메일로 보내
              개선에 활용해도 될까요?
            </p>
            <div className="consent-preview">
              <strong>전송 내용</strong>
              <p>{buildPreview(pendingFeedback.question)}</p>
              <p>{buildPreview(pendingFeedback.answer)}</p>
            </div>
            <div className="consent-actions">
              <button type="button" onClick={dismissFeedbackEmail} disabled={isSendingFeedback}>
                아니요
              </button>
              <button type="button" className="primary" onClick={submitFeedbackEmail} disabled={isSendingFeedback}>
                {isSendingFeedback ? "전송 중" : "동의하고 전송"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}

function MessageText({ message, onAskSuggestion }) {
  const [visibleText, setVisibleText] = useState(message.meta?.animate ? "" : message.content);
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [feedbackBurst, setFeedbackBurst] = useState(null);
  const [isFolded, setIsFolded] = useState(false);
  const isInitialAssistantMessage = message.role === "assistant" && message.meta?.tool === "ready";

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

  function toggleFeedback(value) {
    setFeedback(feedback === value ? null : value);
    setFeedbackBurst({ value, id: Date.now() });
  }

  return (
    <>
      {isFolded ? (
        <p className="message-preview">{buildPreview(message.content)}</p>
      ) : (
        <>
          <div className="message-body">{formatAnswerText(visibleText)}</div>
          <ChartPanel chart={message.meta?.chart} compact />
          <SuggestionPanel suggestions={message.meta?.suggestions} onAskSuggestion={onAskSuggestion} />
          <SourcePanel references={message.meta?.references} />
        </>
      )}
      {!isInitialAssistantMessage ? (
        <div className="message-actions" aria-label="답변 작업">
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
            className={`feedback-button${feedback === "up" ? " active" : ""}`}
            onClick={() => toggleFeedback("up")}
            aria-label="좋아요"
            title="좋아요"
          >
            👍
            {feedbackBurst?.value === "up" ? (
              <span key={feedbackBurst.id} className="feedback-burst" aria-hidden="true">👍</span>
            ) : null}
          </button>
          <button
            type="button"
            className={`feedback-button${feedback === "down" ? " active" : ""}`}
            onClick={() => toggleFeedback("down")}
            aria-label="비추천"
            title="비추천"
          >
            👎
            {feedbackBurst?.value === "down" ? (
              <span key={feedbackBurst.id} className="feedback-burst" aria-hidden="true">👎</span>
            ) : null}
          </button>
        </div>
      ) : null}
    </>
  );
}

function SuggestionPanel({ suggestions, onAskSuggestion }) {
  if (!suggestions?.length) return null;
  return (
    <div className="suggestion-panel" aria-label="다시 시도할 수 있는 질문">
      <strong>이 질문으로 다시 시도해볼 수 있습니다.</strong>
      <div>
        {suggestions.map((suggestion) => (
          <button key={suggestion} type="button" onClick={() => onAskSuggestion?.(suggestion)}>
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

function SourcePanel({ references }) {
  if (!references?.length) return null;
  return (
    <div className="source-panel" aria-label="답변 출처">
      <strong>출처</strong>
      <div className="source-list">
        {references.map((reference, index) => (
          <a
            key={`${reference.source_url}-${index}`}
            className={`source-item${reference.image_url ? "" : " no-image"}`}
            href={reference.source_url}
            target="_blank"
            rel="noreferrer"
          >
            {reference.image_url ? (
              <img src={reference.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
            ) : null}
            <span>
              <b>{reference.title || `출처 ${index + 1}`}</b>
              {reference.snippet ? <em>{reference.snippet}</em> : null}
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}

function LoadingTrace({ activeStep }) {
  const steps = [
    "질문 의도와 맥락을 해석하고 있습니다.",
    "필요한 재무제표, 뉴스, 공시 또는 주가 데이터를 고르고 있습니다.",
    "계산 툴에서 지표와 비교 대상을 처리하고 있습니다.",
    "답변에 필요한 그래프와 핵심 문장을 정리하고 있습니다.",
  ];
  return (
    <div className="loading-trace" aria-label="실시간 처리 과정">
      {steps.map((step, index) => (
        <div key={step} className={index <= activeStep ? "active" : undefined}>
          <span>{index + 1}</span>
          <p>{step}</p>
        </div>
      ))}
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

async function readAttachment(file) {
  const maxBytes = 7 * 1024 * 1024;
  if (file.size > maxBytes) {
    throw new Error("첨부파일은 7MB 이하만 업로드할 수 있습니다.");
  }
  const textTypes = ["text/", "application/json", "text/csv", "application/csv"];
  const isText = textTypes.some((type) => file.type.startsWith(type) || file.type === type) || /\.(txt|md|csv|json)$/i.test(file.name);
  const base = {
    name: file.name,
    type: file.type || inferMimeType(file.name),
    size: file.size,
  };
  if (isText) {
    return { ...base, text: await file.text() };
  }
  const dataUrl = await readFileAsDataUrl(file);
  const [, data = ""] = dataUrl.split(",", 2);
  return { ...base, data };
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("파일을 읽지 못했습니다."));
    reader.readAsDataURL(file);
  });
}

function inferMimeType(fileName) {
  if (/\.pdf$/i.test(fileName)) return "application/pdf";
  if (/\.png$/i.test(fileName)) return "image/png";
  if (/\.jpe?g$/i.test(fileName)) return "image/jpeg";
  if (/\.webp$/i.test(fileName)) return "image/webp";
  return "application/octet-stream";
}

function buildPreview(content) {
  const compact = content.replace(/\s+/g, " ").trim();
  if (!compact) return "접힌 답변입니다.";
  return compact.length > 120 ? `${compact.slice(0, 120)}...` : compact;
}

function shouldAskFeedbackConsent(data, answer) {
  const status = data?.calculation?.status || data?.status;
  const failureStatuses = new Set([
    "error",
    "missing_data",
    "needs_company",
    "no_data",
    "needs_latest_disclosure",
    "missing_config",
  ]);
  if (failureStatuses.has(status)) return true;

  const normalized = String(answer || "").replace(/\s+/g, " ");
  return [
    "찾지 못했습니다",
    "확인할 수 없습니다",
    "제공하기 어렵습니다",
    "분석하기 어렵습니다",
    "어렵습니다",
    "어려워",
    "데이터가 부족",
    "정보가 부족",
    "답변을 생성하지 못했습니다",
    "연결하지 못했습니다",
  ].some((phrase) => normalized.includes(phrase));
}

function shouldShowAlternativeQuestions(answer, data) {
  const normalized = String(answer || "").replace(/\s+/g, " ").toLowerCase();
  if (normalized.includes("load failed")) return true;
  const status = data?.calculation?.status || data?.status;
  const failureStatuses = new Set([
    "error",
    "missing_data",
    "needs_company",
    "no_data",
    "needs_latest_disclosure",
    "missing_config",
    "price_fetch_error",
    "missing_dependency",
  ]);
  if (failureStatuses.has(status)) return true;
  return [
    "백엔드 서버에 연결하지 못했습니다",
    "request failed",
    "찾지 못했습니다",
    "확인할 수 없습니다",
    "제공하기 어렵습니다",
    "분석하기 어렵습니다",
    "계산하기 어렵습니다",
    "어렵습니다",
    "어려워",
    "계산하기에는 정보가 부족",
    "현재 확보된 자료만으로는",
    "데이터가 부족",
    "정보가 부족",
    "자료가 부족",
    "정확한 답변이 어렵",
    "정확한 pbr",
  ].some((phrase) => normalized.includes(phrase.toLowerCase()));
}

function buildDisplayReferences(references) {
  const seen = new Set();
  return (references || [])
    .filter((reference) => reference?.source_url)
    .filter((reference) => {
      const key = reference.source_url;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 3)
    .map((reference) => ({
      title: cleanReferenceTitle(reference.title),
      source_url: reference.source_url,
      image_url: reference.image_url,
      snippet: buildPreview(reference.snippet || ""),
    }));
}

function cleanReferenceTitle(title) {
  return String(title || "")
    .replace(/^news_/, "")
    .replace(/_/g, " ")
    .trim();
}

function buildAlternativeQuestions(question) {
  const companyNames = extractCompanies(question);
  const metric = extractMetric(question);
  const contextKeyword = extractContextKeyword(question, metric);

  if (companyNames.length >= 2) {
    const first = companyNames[0];
    const second = companyNames[1];
    return [
      `${first}와 ${second}의 최근 ${contextKeyword} 비교 추이를 분석해줘`,
      `${first}의 최근 ${contextKeyword}과 매출액을 함께 비교해줘`,
    ];
  }

  if (companyNames.length === 1) {
    const company = companyNames[0];
    if (metric === "PBR") {
      return [
        `PBR을 구하는 공식과 해석 방법을 알려줘`,
        `${company}의 PBR 계산에 필요한 주가와 BPS를 확인해줘`,
      ];
    }
    const isPriceRelated = ["주가", "종가", "가격"].some(term => question.includes(term));
    if (isPriceRelated) {
      return [
        `${company}의 최근 주가 변동성 및 최대낙폭(MDD)을 계산해줘`,
        `${company}의 최근 5년 주가를 가지고 다음 주가를 예측해줘`,
      ];
    }
    return [
      `${company}의 향후 ${contextKeyword} 전망을 계산해줘`,
      `${company}의 최근 ${contextKeyword}과 매출액을 비교해줘`,
    ];
  }

  return [
    `${contextKeyword}을 계산하는 데 필요한 재무제표 계정은 무엇입니까?`,
    `최근 5개년 ${contextKeyword} 추이 전망을 분석해줘`,
  ];
}

function extractCompanies(question) {
  const aliases = [
    ["삼성전자", ["삼성전자", "삼전"]],
    ["SK하이닉스", ["sk하이닉스", "SK하이닉스", "하이닉스"]],
    ["한화에어로스페이스", ["한화에어로스페이스", "한화에어로"]],
    ["한국항공우주", ["한국항공우주", "KAI"]],
    ["LIG넥스원", ["LIG넥스원", "lig넥스원"]],
    ["현대로템", ["현대로템"]],
    ["셀트리온", ["셀트리온"]],
    ["LG에너지솔루션", ["LG에너지솔루션", "lg에너지솔루션"]],
    ["현대차", ["현대차", "현대자동차"]],
    ["기아", ["기아"]],
  ];
  const lowered = question.toLowerCase();
  const found = [];
  aliases.forEach(([name, tokens]) => {
    if (tokens.some((token) => lowered.includes(token.toLowerCase())) && !found.includes(name)) {
      found.push(name);
    }
  });
  return found;
}

function extractMetric(question) {
  const compact = question.replace(/\s+/g, "").toLowerCase();
  const rules = [
    ["매출액영업이익률", ["매출액영업이익률", "영업이익률", "영업마진"]],
    ["매출액순이익률", ["매출액순이익률", "순이익률", "순이익마진"]],
    ["매출액이익률", ["매출이익률", "매출액이익률", "이익률"]],
    ["매출원가율", ["매출원가율", "원가율"]],
    ["판관비율", ["판관비율", "판매관리비율", "판매비와관리비율"]],
    ["매출액", ["매출액", "매출"]],
    ["영업이익", ["영업이익"]],
    ["당기순이익", ["당기순이익", "순이익"]],
    ["주가", ["주가", "종가"]],
    ["PBR", ["pbr", "주가순자산비율", "주가순자산배율"]],
    ["부채비율", ["부채비율"]],
    ["유동비율", ["유동비율"]],
  ];
  const match = rules.find(([, tokens]) => tokens.some((token) => compact.includes(token.toLowerCase())));
  return match ? match[0] : "주요 재무계정";
}

function extractContextKeyword(question, metric) {
  const compact = question.replace(/\s+/g, "").toLowerCase();
  const contextRules = [
    ["차입과 유동비율", ["차입", "차입금", "상환"]],
    ["유동자산과 유동부채", ["유동자산", "유동부채"]],
    ["부채와 유동비율", ["부채", "안정성"]],
    ["매출원가율과 판관비율", ["원가", "판관비", "판매비와관리비"]],
    ["주가와 PBR", ["pbr", "주가순자산"]],
    ["주가 흐름", ["주가", "종가"]],
  ];
  const match = contextRules.find(([, tokens]) => tokens.some((token) => compact.includes(token.toLowerCase())));
  return match ? match[0] : metric;
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
  const pointRadius = allPoints.length >= 100 ? 1.8 : 3.4;
  const forecastRadius = allPoints.length >= 100 ? 2.6 : 4.5;
  const maxMarkerRadius = allPoints.length >= 100 ? 3.2 : 5.2;
  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const rawMinY = Math.min(...yValues);
  const rawMaxY = Math.max(...yValues);
  const paddingY = Math.max((rawMaxY - rawMinY) * 0.12, Math.abs(rawMaxY) * 0.03, 1);
  const minY = rawMinY >= 0 ? Math.max(0, rawMinY - paddingY) : rawMinY - paddingY;
  const maxY = rawMaxY + paddingY;
  const yRange = maxY - minY || 1;
  const xRange = maxX - minX || 1;
  const axisBreak = buildAxisBreak(yValues, minY, maxY, padding, height);
  let rawTicks = [];
  if (axisBreak) {
    rawTicks = [minY, axisBreak.lowerEnd, (axisBreak.lowerEnd + axisBreak.upperStart) / 2, axisBreak.upperStart, maxY];
  } else {
    rawTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => minY + yRange * ratio);
  }
  
  let formattedTicks = [];
  if (chart.unit === "PERCENT" || chart.unit === "MULTIPLE") {
    formattedTicks = rawTicks.map((t) => Math.round(t * 10) / 10);
  } else {
    formattedTicks = rawTicks.map((t) => {
      const absVal = Math.abs(t);
      if (absVal >= 1_0000_0000_0000) {
        return Math.round(t / 1000_0000_0000) * 1000_0000_0000;
      } else if (absVal >= 1_0000_0000) {
        return Math.round(t / 1000_0000) * 1000_0000;
      } else if (absVal >= 10_000) {
        return Math.round(t / 1000) * 1000;
      }
      return Math.round(t);
    });
  }
  const yTicks = [...new Set(formattedTicks)].sort((a, b) => a - b);
  const xTicks = buildXTicks(allPoints);
  const maxMarkers = buildMaxPointMarkers(chart.datasets, rawMaxY);

  const scaleX = (value) => padding.left + ((value - minX) / xRange) * (width - padding.left - padding.right);
  const scaleY = (value) => {
    if (axisBreak) return scaleBrokenY(value, axisBreak);
    return height - padding.bottom - ((value - minY) / yRange) * (height - padding.top - padding.bottom);
  };

  return (
    <div className="line-chart">
      <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={chart.title}>
        {yTicks.map((tick) => (
          <g key={tick}>
            <line className="chart-grid" x1={padding.left} y1={scaleY(tick)} x2={width - padding.right} y2={scaleY(tick)} />
            <text x={padding.left - 8} y={scaleY(tick) + 3} textAnchor="end">{formatChartValue(tick, chart.unit)}</text>
          </g>
        ))}
        {axisBreak ? (
          <g className="axis-break" aria-label="중간 축 생략">
            <path d={`M ${padding.left - 9} ${axisBreak.gapMiddle - 4} q 4 -5 8 0 t 8 0`} />
            <path d={`M ${padding.left + 8} ${axisBreak.gapMiddle - 4} q 4 -5 8 0 t 8 0`} />
            <text x={padding.left - 36} y={axisBreak.gapMiddle + 4} textAnchor="middle">~</text>
          </g>
        ) : null}
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
                  r={point.forecast ? forecastRadius : pointRadius}
                >
                  <title>{`${dataset.label} ${point.label}: ${point.display}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
        {maxMarkers.map((marker) => {
          const x = scaleX(marker.point.x);
          const y = scaleY(marker.point.y);
          const labelY = y < padding.top + 18 ? y + 18 : y - 10;
          const textAnchor = x > width - padding.right - 52 ? "end" : x < padding.left + 52 ? "start" : "middle";
          const textX = textAnchor === "end" ? x - 8 : textAnchor === "start" ? x + 8 : x;
          return (
            <g key={`${marker.datasetKey}-${marker.point.x}-max`} className="max-point-marker">
              <circle cx={x} cy={y} r={maxMarkerRadius}>
                <title>{`최댓값 ${marker.datasetLabel} ${marker.point.label}: ${marker.point.display}`}</title>
              </circle>
              <text x={textX} y={labelY} textAnchor={textAnchor}>
                {marker.point.display}
              </text>
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

function buildMaxPointMarkers(datasets, rawMaxY) {
  const markers = [];
  datasets.forEach((dataset) => {
    dataset.points.forEach((point) => {
      if (point.y === rawMaxY) {
        markers.push({
          datasetKey: dataset.key,
          datasetLabel: dataset.label,
          point,
        });
      }
    });
  });
  return markers.slice(0, 3);
}

function buildAxisBreak(values, minY, maxY, padding, height) {
  if (minY < 0 || maxY <= 0) return null;
  const positives = [...new Set(values.filter((value) => value > 0).sort((a, b) => a - b))];
  if (positives.length < 3) return null;

  let breakPair = null;
  for (let index = 0; index < positives.length - 1; index += 1) {
    const low = positives[index];
    const high = positives[index + 1];
    const ratio = high / Math.max(low, 1);
    const gapShare = (high - low) / Math.max(maxY - minY, 1);
    if (ratio >= 4 && gapShare >= 0.35 && (!breakPair || ratio > breakPair.ratio)) {
      breakPair = { low, high, ratio };
    }
  }
  if (!breakPair) return null;

  const plotTop = padding.top;
  const plotBottom = height - padding.bottom;
  const plotHeight = plotBottom - plotTop;
  const gapSize = 18;
  const lowerHeight = plotHeight * 0.44;
  const upperHeight = plotHeight - lowerHeight - gapSize;
  const upperTop = plotTop;
  const upperBottom = upperTop + upperHeight;
  const gapTop = upperBottom;
  const gapBottom = gapTop + gapSize;
  const lowerTop = gapBottom;
  const lowerBottom = plotBottom;

  return {
    minY,
    maxY,
    lowerEnd: breakPair.low,
    upperStart: breakPair.high,
    upperTop,
    upperBottom,
    lowerTop,
    lowerBottom,
    upperHeight,
    lowerHeight,
    gapMiddle: gapTop + gapSize / 2,
  };
}

function scaleBrokenY(value, axisBreak) {
  if (value <= axisBreak.lowerEnd) {
    const range = axisBreak.lowerEnd - axisBreak.minY || 1;
    return axisBreak.lowerBottom - ((value - axisBreak.minY) / range) * axisBreak.lowerHeight;
  }
  if (value >= axisBreak.upperStart) {
    const range = axisBreak.maxY - axisBreak.upperStart || 1;
    return axisBreak.upperBottom - ((value - axisBreak.upperStart) / range) * axisBreak.upperHeight;
  }
  return axisBreak.gapMiddle;
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
  if (unit === "MULTIPLE") return `${value.toFixed(1)}배`;
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
            <div
              className={`bar-fill${bar.value < 0 ? " negative" : ""}`}
              style={{
                width: `${Math.max(4, (Math.abs(bar.value) / maxValue) * 50)}%`,
                left: bar.value < 0 ? `${50 - (Math.abs(bar.value) / maxValue) * 50}%` : "50%",
              }}
            />
          </div>
          <strong>{bar.display}</strong>
        </div>
      ))}
    </div>
  );
}
