import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { BarChart as EChartsBarChart, LineChart as EChartsLineChart } from "echarts/charts";
import {
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkPointComponent,
  TooltipComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import katex from "katex";
import "katex/dist/katex.min.css";

echarts.use([
  EChartsLineChart,
  EChartsBarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkPointComponent,
  AriaComponent,
  SVGRenderer,
]);

const API_HOSTNAME = import.meta.env?.VITE_API_HOSTNAME;
const API_URL =
  import.meta.env?.VITE_API_URL ||
  (API_HOSTNAME ? `https://${API_HOSTNAME}` : "http://localhost:8000");

const RETRYABLE_STATUS_CODES = new Set([502, 503, 504]);

function isNetworkLoadError(error) {
  const message = String(error?.message || "").toLowerCase();
  return ["failed to fetch", "load failed", "networkerror", "network request failed"].some((text) => message.includes(text));
}

function retryDelay(ms, signal) {
  return new Promise((resolve, reject) => {
    const timerId = window.setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      window.clearTimeout(timerId);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  });
}

async function fetchWithRetry(url, options = {}, retryOptions = {}) {
  const attempts = retryOptions.attempts || 3;
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(url, options);
      if (!RETRYABLE_STATUS_CODES.has(response.status) || attempt === attempts - 1) {
        return response;
      }
      lastError = new Error(`Temporary server error (${response.status})`);
    } catch (error) {
      if (error?.name === "AbortError" || !isNetworkLoadError(error) || attempt === attempts - 1) {
        throw error;
      }
      lastError = error;
    }
    retryOptions.onRetry?.(attempt + 1);
    await retryDelay(1500 * (attempt + 1), options.signal);
  }
  throw lastError || new Error("Network request failed");
}

function formatMessageTimestamp(dateObj) {
  const hours = dateObj.getHours();
  const minutes = dateObj.getMinutes();
  const ampm = hours >= 12 ? "오후" : "오전";
  const displayHours = hours % 12 || 12;
  const displayMinutes = minutes.toString().padStart(2, "0");
  
  const today = new Date();
  const isToday =
    dateObj.getDate() === today.getDate() &&
    dateObj.getMonth() === today.getMonth() &&
    dateObj.getFullYear() === today.getFullYear();
    
  if (isToday) {
    return `오늘 ${ampm} ${displayHours}:${displayMinutes}`;
  } else {
    return `${dateObj.getMonth() + 1}월 ${dateObj.getDate()}일 ${ampm} ${displayHours}:${displayMinutes}`;
  }
}

const INITIAL_MESSAGE = {
  role: "assistant",
  content: "안녕하세요. 기업재무 챗봇입니다. 무엇이 궁금하세요?",
  timestamp: formatMessageTimestamp(new Date()),
  meta: {
    tool: "ready",
    status: "ok",
  },
};

const FALLBACK_RECOMMENDED_QUESTIONS = [
  "삼성전자의 최근 3개년 매출액과 영업이익 추이를 분석해줘",
  "SK하이닉스의 최근 2개년 유동비율과 당좌비율을 알려줘",
  "셀트리온의 최근 1년 주가 변동성과 최대낙폭(MDD)을 계산해줘",
  "한화에어로스페이스의 최근 5개년 매출 추이로 2026년 매출을 전망해줘",
  "LIG넥스원의 최근 3개년 주요 재무지표 추이를 분석해줘",
  "에스엠의 최근 1년 주가 수익률과 변동성을 계산해줘",
  "와이지엔터테인먼트의 최근 3개년 매출액과 영업이익을 비교해줘",
  "삼성전자의 최근 5개년 PER 추이를 계산해줘",
  "SK하이닉스의 최근 3년 주가 흐름을 차트로 보여줘",
  "SK하이닉스의 WACC를 7~11%, 영구성장률을 1~4%로 변경하면서 적정 주가 민감도 표를 만들어줘.",
  "셀트리온의 최근 3개년 부채비율과 ROE 추이를 분석해줘",
  "방산 산업의 최근 주요 동향과 뉴스 흐름을 분석해줘"
];

export default function ChatUI() {
  const [messages, setMessages] = useState([INITIAL_MESSAGE]);
  const [input, setInput] = useState("");
  const [attachedFile, setAttachedFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStartedAt, setLoadingStartedAt] = useState(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [activeStep, setActiveStep] = useState(0);
  const [displayedActiveStep, setDisplayedActiveStep] = useState(0);
  const [stepTexts, setStepTexts] = useState(["질문의 의도와 맥락을 해석하고 있습니다."]);

  useEffect(() => {
    if (!isLoading) {
      setDisplayedActiveStep(0);
      return;
    }
    if (displayedActiveStep < activeStep) {
      const timer = setTimeout(() => {
        setDisplayedActiveStep((prev) => prev + 1);
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [activeStep, displayedActiveStep, isLoading]);

  const [feedbackNotice, setFeedbackNotice] = useState("");
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);
  const abortControllerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const recommendedSidebarRef = useRef(null);

  useEffect(() => {
    let requestRef;
    let currentY = window.scrollY;

    const updateElasticScroll = () => {
      const targetY = window.scrollY;
      currentY += (targetY - currentY) * 0.09;

      if (recommendedSidebarRef.current) {
        const offset = (currentY - targetY) * 0.15;
        recommendedSidebarRef.current.style.transform = `translateY(${offset}px)`;
      }
      requestRef = requestAnimationFrame(updateElasticScroll);
    };

    requestRef = requestAnimationFrame(updateElasticScroll);
    return () => cancelAnimationFrame(requestRef);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const [recommendedQuestions, setRecommendedQuestions] = useState([]);
  const canSubmit = (input.trim().length > 0 || Boolean(attachedFile)) && !isLoading;
  const isInitialState = messages.filter((m) => m.role === "user").length === 0;

  const fetchRecommendedQuestions = useCallback(async () => {
    for (const path of ["/api/recommended-questions", "/api/trending-questions"]) {
      try {
        const separator = path.includes("?") ? "&" : "?";
        const response = await fetch(`${API_URL}${path}${separator}_=${Date.now()}`, {
          cache: "no-store",
          headers: { "Cache-Control": "no-cache" },
        });
        if (!response.ok) continue;
        const data = await response.json();
        if (Array.isArray(data.questions) && data.questions.length > 0) {
          setRecommendedQuestions(data.questions.slice(0, 5));
          return;
        }
      } catch (error) {
        console.warn(`Failed to fetch recommended questions from ${path}`, error);
      }
    }
    setRecommendedQuestions(buildFallbackRecommendedQuestions());
  }, []);

  useEffect(() => {
    fetchWithRetry(`${API_URL}/health`, { cache: "no-store" }, { attempts: 2 }).catch((error) => {
      console.warn("Backend warm-up failed", error);
    });
  }, []);

  useEffect(() => {
    fetchRecommendedQuestions();
    const interval = window.setInterval(fetchRecommendedQuestions, 600000);
    return () => clearInterval(interval);
  }, [fetchRecommendedQuestions]);

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

  async function sendMessage(nextInput = input, replaceActive = false) {
    const question = nextInput.trim();
    if (!question && !attachedFile) return;
    if (isLoading && !replaceActive) return;
    if (isLoading && replaceActive && abortControllerRef.current) {
      abortControllerRef.current.replacedByRecommendation = true;
      abortControllerRef.current.abort();
    }
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
        timestamp: formatMessageTimestamp(new Date()),
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
    setDisplayedActiveStep(0);
    setStepTexts(["질문의 의도와 맥락을 해석하고 있습니다."]);
    setIsLoading(true);
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const chatRequestOptions = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: displayQuestion, history, attachment }),
        signal: abortController.signal,
      };
      let response = await fetchWithRetry(`${API_URL}/api/chat`, chatRequestOptions, {
        attempts: 3,
        onRetry: () => setStepTexts((prev) => {
          const next = [...prev];
          next[Math.max(0, activeStep)] = "서버 연결을 다시 시도하고 있습니다.";
          return next;
        }),
      });

      if (!response.ok) {
        throw new Error("Request failed");
      }

      let data = null;

      const processEventBlock = (block) => {
        const eventLines = block.split(/\r?\n/);
        const eventName = eventLines
          .find((line) => line.startsWith("event:"))
          ?.slice("event:".length)
          .trim();
        const rawData = eventLines
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice("data:".length).trimStart())
          .join("\n");

        if (!eventName || !rawData) return;

        let parsed;
        try {
          parsed = JSON.parse(rawData);
        } catch (error) {
          console.error("Failed to parse event stream data", error);
          return;
        }

        if (eventName === "step") {
          setActiveStep(parsed.step_index);
          if (parsed.message) {
            setStepTexts((prev) => {
              const next = [...prev];
              next[parsed.step_index] = parsed.message;
              return next;
            });
          }
        } else if (eventName === "result") {
          data = parsed;
        } else if (eventName === "error") {
          const streamError = new Error(parsed.message || "서버에서 답변을 생성하지 못했습니다.");
          streamError.suggestions = Array.isArray(parsed.suggestions) ? parsed.suggestions : [];
          throw streamError;
        }
      };

      const consumeEventStream = async (streamResponse) => {
        const reader = streamResponse.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

          const eventBlocks = buffer.split(/\r?\n\r?\n/);
          buffer = eventBlocks.pop() || "";
          eventBlocks.filter(Boolean).forEach(processEventBlock);

          if (done) {
            if (buffer.trim()) processEventBlock(buffer);
            break;
          }
        }
      };

      await consumeEventStream(response);

      if (!data) {
        setStepTexts((prev) => [...prev, "끊긴 답변 연결을 다시 복구하고 있습니다."]);
        response = await fetchWithRetry(`${API_URL}/api/chat`, chatRequestOptions, { attempts: 2 });
        if (!response.ok) throw new Error("Request failed");
        await consumeEventStream(response);
      }
      if (!data) {
        throw new Error("서버 연결이 끝까지 유지되지 않았습니다. 잠시 후 다시 시도해 주세요.");
      }

      const answer = data.answer || "답변을 생성하지 못했습니다.";
      const needsCompany = data.calculation?.status === "needs_company";
      const serverSuggestions = Array.isArray(data.suggestions)
        ? data.suggestions.filter((suggestion) => suggestion && suggestion !== displayQuestion).slice(0, 2)
        : [];
      setMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: answer,
          timestamp: formatMessageTimestamp(new Date()),
          meta: {
            animate: true,
            question: displayQuestion,
            tool: data.tool,
            status: data.calculation?.status,
            references: buildDisplayReferences(data.references),
            chart: data.chart,
            trace: data.trace || [],
            suggestions: needsCompany
              ? buildExampleCompanies(data.calculation?.suggested_companies)
              : shouldShowAlternativeQuestions(answer, data)
                ? serverSuggestions
                : [],
            suggestionTitle: needsCompany ? "예시 기업들" : undefined,
            failureConsent: shouldAskFeedbackConsent(data, answer)
              ? {
                  question: displayQuestion,
                  answer,
                  tool: data.tool,
                  status: data.calculation?.status || data.status || "error",
                }
              : null,
          },
        },
      ]);
    } catch (error) {
      if (error.name === "AbortError" && abortController.replacedByRecommendation) return;
      const answer =
        error.name === "AbortError"
          ? "요청을 취소했습니다."
          : isNetworkLoadError(error)
            ? "분석 중 서버 연결이 끊겼습니다. 무료 서버가 재시작 중이거나 일시적으로 사용량이 높을 수 있으니 잠시 후 다시 시도해 주세요."
            : error.message;
      const errorSuggestions = Array.isArray(error.suggestions)
        ? error.suggestions.filter((suggestion) => suggestion && suggestion !== displayQuestion).slice(0, 2)
        : [];
      setMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: answer,
          timestamp: formatMessageTimestamp(new Date()),
          meta: {
            animate: true,
            question: displayQuestion,
            tool: error.name === "AbortError" ? "cancelled" : "network",
            status: error.name === "AbortError" ? "cancelled" : "error",
            suggestions: error.name === "AbortError" ? [] : errorSuggestions,
            failureConsent: error.name === "AbortError"
              ? null
              : { question: displayQuestion, answer, tool: "network", status: "error" },
          },
        },
      ]);
    } finally {
      if (abortControllerRef.current === abortController) {
        abortControllerRef.current = null;
        setIsLoading(false);
        setLoadingStartedAt(null);
        window.requestAnimationFrame(() => inputRef.current?.focus());
      }
    }
  }

  function cancelMessage() {
    abortControllerRef.current?.abort();
  }

  function handleRecommendedQuestionClick(questionText) {
    sendMessage(questionText, true);
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div>
          {!isInitialState && <p className="eyebrow">Corporate Finance Bot</p>}
        </div>
        <p className="analysis-disclaimer">
          분석 결과는 과거 데이터와 가정을 기반으로 한 단순 추정치이며, 실제 결과와 다를 수 있습니다.
        </p>
      </aside>

      {isInitialState ? (
        <section className="initial-hero-panel">
          <div className="initial-hero-container">
            <h1 className="hero-logo-title">Corporate Finance Bot</h1>
            
            <div className="initial-recommend-section">
              <div className="recommend-title">
                <span className="recommend-icon">💡</span>
                <span>이런 질문은 어떠세요?</span>
              </div>
              <div className="recommend-grid">
                <div className="recommend-row upper-row">
                  {recommendedQuestions.slice(0, 3).map((q, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className="recommend-pill-btn"
                      onClick={() => handleRecommendedQuestionClick(q)}
                    >
                      {q}
                    </button>
                  ))}
                </div>
                <div className="recommend-row lower-row">
                  {recommendedQuestions.slice(3, 5).map((q, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className="recommend-pill-btn"
                      onClick={() => handleRecommendedQuestionClick(q)}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <form
              className="capsule-composer"
              onSubmit={(event) => {
                event.preventDefault();
                if (isLoading) return;
                sendMessage();
              }}
            >
              {attachedFile ? (
                <div className="capsule-attachment-chip">
                  <span>{attachedFile.name}</span>
                  <button type="button" onClick={() => setAttachedFile(null)} aria-label="첨부파일 제거">
                    ✕
                  </button>
                </div>
              ) : null}
              
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="이곳에 질문을 입력하세요."
                className="capsule-input"
                disabled={isLoading}
              />
              
              <input
                ref={fileInputRef}
                type="file"
                className="file-input"
                style={{ display: 'none' }}
                accept=".txt,.md,.csv,.json,.pdf,image/*"
                onChange={(event) => setAttachedFile(event.target.files?.[0] || null)}
              />
              
              <div className="capsule-actions">
                <button
                  type="button"
                  className="capsule-attach-btn"
                  data-tooltip="문제 업로드"
                  aria-label="문제 업로드"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isLoading}
                  style={{ background: 'transparent', border: '1px solid var(--border)', borderRadius: '6px', width: '28px', height: '28px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', padding: 0, color: 'var(--text-muted)' }}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                  </svg>
                </button>
                <button
                  type="submit"
                  className="capsule-send-btn"
                  disabled={!canSubmit}
                  data-tooltip="질문 전송"
                  aria-label="질문 전송"
                  style={{ background: 'transparent', border: '1px solid var(--border)', borderRadius: '6px', width: '28px', height: '28px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', padding: 0, color: canSubmit ? 'var(--accent)' : 'var(--border)' }}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ transform: 'translate(1px, -1px)' }}>
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                </button>
              </div>
            </form>
            <p className="server-start-notice">
              첫 접속 시 서버 시작에 최대 2분이 소요 될 수 있습니다. 추천 질문을 선택해 챗봇을 시작해 보세요.
            </p>
          </div>
        </section>
      ) : (
        <>
          <section className="chat-panel" aria-label="채팅">
        <div className="message-list">
          {messages
            .filter((msg, idx) => !(idx === 0 && msg.role === "assistant"))
            .map((message, index) => (
              <div key={`${message.role}-${index}`} className="message-container" style={{ display: 'flex', flexDirection: 'column', width: '100%', marginBottom: '12px' }}>
                {message.role === "user" && message.timestamp && (
                  <span className="message-time-label" style={{
                    fontSize: '13px',
                    color: 'var(--text-muted)',
                    alignSelf: 'flex-end',
                    margin: '5px 10px 4px 0',
                  }}>
                    {message.timestamp}
                  </span>
                )}
                <article className={`message ${message.role}`}>
                  <MessageText message={message} onAskSuggestion={handleRecommendedQuestionClick} />
                </article>
              </div>
            ))}

          {isLoading ? (
            <article className="message assistant loading" style={{ paddingTop: '2px', paddingBottom: '2px', marginTop: '4px' }}>
              <LoadingTrace activeStep={displayedActiveStep} stepTexts={stepTexts} />
            </article>
          ) : null}
          <div ref={messagesEndRef} />
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
            placeholder="이곳에 질문을 입력하세요."
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
            data-tooltip="문제 업로드"
            aria-label="문제 업로드"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            style={{ background: 'transparent', border: '1px solid var(--border)', borderRadius: '9px', width: '44px', height: '44px', minHeight: '44px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', padding: 0, color: 'var(--text-muted)', alignSelf: 'end' }}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
          <button
            type={isLoading ? "button" : "submit"}
            className={isLoading ? "send-button cancel-button" : "send-button"}
            disabled={!isLoading && !canSubmit}
            onClick={isLoading ? cancelMessage : undefined}
            data-tooltip={isLoading ? "질문 취소" : "질문 전송"}
            aria-label={isLoading ? "질문 취소" : "질문 전송"}
            style={{ background: 'transparent', border: '1px solid var(--border)', borderRadius: '9px', width: '44px', height: '44px', minHeight: '44px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', padding: 0, color: isLoading ? '#e98787' : (canSubmit ? '#d99572' : '#d8ccc4'), alignSelf: 'end' }}
          >
            {isLoading ? (
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            ) : (
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ transform: 'translate(1px, -1px)' }}>
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            )}
          </button>
        </form>
      </section>

      <aside ref={recommendedSidebarRef} className="recommended-sidebar" aria-label="추천 질문">
        <div className="recommended-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="recommended-icon" aria-hidden="true">💡</span>
            <strong>이런 질문은 어떠세요?</strong>
          </div>
          <button
            type="button"
            className="recommend-refresh-btn"
            onClick={fetchRecommendedQuestions}
            data-tooltip="질문 재생성"
            aria-label="질문 재생성"
            style={{
              background: 'transparent',
              border: '1px solid var(--border)',
              borderRadius: '50%',
              width: '24px',
              height: '24px',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: 'var(--text-muted)',
              transition: 'border-color 160ms, color 160ms',
              padding: 0
            }}
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
            </svg>
          </button>
        </div>
        <div className="recommended-list">
          {recommendedQuestions.map((question, index) => (
            <button
              key={question}
              type="button"
              className="recommended-card"
              onClick={() => handleRecommendedQuestionClick(question)}
            >
              <span className="recommended-number">{index + 1}</span>
              <span className="recommended-text">{question}</span>
            </button>
          ))}
          {recommendedQuestions.length === 0 && (
            <div className="recommended-empty" role="status">
              추천 질문을 불러오는 중입니다...
            </div>
          )}
        </div>
      </aside>
      </>
      )}

      {feedbackNotice ? (
        <div className="feedback-toast" role="status">
          {feedbackNotice}
        </div>
      ) : null}
    </main>
  );
}

function buildFallbackRecommendedQuestions() {
  const newsQuestion = "방산 산업의 최근 주요 동향과 뉴스 흐름을 분석해줘";
  const stockQuestion = "SK하이닉스의 최근 3년 주가 흐름을 차트로 보여줘";
  const advancedQuestion = "SK하이닉스의 WACC를 7~11%, 영구성장률을 1~4%로 변경하면서 적정 주가 민감도 표를 만들어줘.";
  const kospi5 = ["삼성전자", "SK하이닉스", "삼성전기", "현대차", "LG에너지솔루션"];

  const selected = [newsQuestion, stockQuestion, advancedQuestion];
  if (!selected.some((question) => kospi5.some((company) => question.includes(company)))) {
    selected.push("삼성전자의 최근 3개년 매출액과 영업이익 추이를 분석해줘");
  }
  const remainingPool = FALLBACK_RECOMMENDED_QUESTIONS
    .filter((question) => {
      if (selected.includes(question)) return false;
      const compact = question.replaceAll(" ", "").toLowerCase();
      const isNews = compact.includes("뉴스");
      const isStock = ["주가", "종가", "최대낙폭", "mdd"].some((token) => compact.includes(token));
      const isAdvanced = ["dcf", "wacc", "영구성장률", "몬테카를로", "스트레스", "최대샤프", "최소분산", "포트폴리오"].some((token) => compact.includes(token));
      return !isNews && !isStock && !isAdvanced;
    })
    .sort(() => Math.random() - 0.5);
  selected.push(...remainingPool.slice(0, 5 - selected.length));
  return selected.sort(() => Math.random() - 0.5);
}

function MessageText({ message, onAskSuggestion }) {
  const [visibleText, setVisibleText] = useState(message.meta?.animate ? "" : message.content);
  const [isTyping, setIsTyping] = useState(Boolean(message.meta?.animate));
  const [copied, setCopied] = useState(false);
  const isInitialAssistantMessage = message.role === "assistant" && message.meta?.tool === "ready";

  useEffect(() => {
    if (!message.meta?.animate) {
      setVisibleText(message.content);
      setIsTyping(false);
      return undefined;
    }

    setVisibleText("");
    setIsTyping(true);
    let index = 0;
    const step = Math.max(2, Math.min(10, Math.floor(message.content.length / 180)));
    const timerId = window.setInterval(() => {
      index = Math.min(message.content.length, index + step);
      setVisibleText(message.content.slice(0, index));
      if (index >= message.content.length) {
        window.clearInterval(timerId);
        setIsTyping(false);
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

  const [shared, setShared] = useState(false);
  async function shareQuestionAndAnswer() {
    const question = message.meta?.question || message.meta?.failureConsent?.question;
    const shareText = [
      question ? `질문\n${question}` : null,
      `답변\n${message.content}`,
    ].filter(Boolean).join("\n\n");

    try {
      if (navigator.share) {
        try {
          await navigator.share({
            title: question ? `금융 챗봇 답변: ${question.slice(0, 40)}` : "금융 챗봇 답변",
            text: shareText,
          });
        } catch (error) {
          if (error?.name === "AbortError") return;
          await navigator.clipboard.writeText(shareText);
        }
      } else {
        await navigator.clipboard.writeText(shareText);
      }
      setShared(true);
      window.setTimeout(() => setShared(false), 1400);
    } catch {
      setShared(false);
    }
  }

  return (
    <>
      <div className="message-body">{formatAnswerText(visibleText)}</div>
      {isTyping ? (
        <div className="answer-writing-dots" aria-label="답변 작성 중">
          <LoadingDots />
        </div>
      ) : null}
      <ChartPanel chart={message.meta?.chart} compact />
      <SuggestionPanel
        suggestions={message.meta?.suggestions}
        title={message.meta?.suggestionTitle}
        onAskSuggestion={onAskSuggestion}
      />
      <SourcePanel references={message.meta?.references} />
      <FailureConsentPanel request={message.meta?.failureConsent} />
      {!isInitialAssistantMessage ? (
        <div className="message-actions" aria-label="답변 작업">
          <button
            type="button"
            className="message-action-btn"
            onClick={copyMessage}
            aria-label="답변 복사"
            data-tooltip={copied ? "복사 완료" : "답변 복사"}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
          </button>
          <button
            type="button"
            className={`message-action-btn${shared ? " active" : ""}`}
            onClick={shareQuestionAndAnswer}
            aria-label="질문과 답변 공유"
            data-tooltip={shared ? "공유 완료" : "답변 공유"}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="18" cy="5" r="3" />
              <circle cx="6" cy="12" r="3" />
              <circle cx="18" cy="19" r="3" />
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
              <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
            </svg>
          </button>
        </div>
      ) : null}
    </>
  );
}

function SuggestionPanel({ suggestions, title, onAskSuggestion }) {
  if (!suggestions?.length) return null;
  return (
    <div className="suggestion-panel" aria-label="다시 시도할 수 있는 질문">
      <strong>{title || "이 질문으로 다시 시도해볼 수 있습니다."}</strong>
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

function FailureConsentPanel({ request }) {
  const [checked, setChecked] = useState(false);
  const [decision, setDecision] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [notice, setNotice] = useState("");

  if (!request) return null;

  async function agreeToCollection() {
    if (!checked || decision || isSubmitting) return;
    setIsSubmitting(true);
    setNotice("");
    try {
      const response = await fetchWithRetry(`${API_URL}/api/failed-question-log`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...request, consent: true }),
      }, { attempts: 3 });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || "서버가 준비되지 않아 기록하지 못했습니다. 잠시 후 다시 시도해 주세요.");
      setDecision("agreed");
      setNotice("감사합니다.");
    } catch (error) {
      setNotice(
        isNetworkLoadError(error)
          ? "서버 연결이 끊겨 기록하지 못했습니다. 잠시 후 다시 시도해 주세요."
          : error.message || "기록하지 못했습니다."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  function declineCollection() {
    if (decision || isSubmitting) return;
    setChecked(false);
    setDecision("declined");
    setNotice("수집하지 않습니다.");
  }

  return (
    <section className="failure-consent" aria-label="실패 질문 수집 동의">
      <strong>답변 개선을 위한 실패 질문 수집</strong>
      <p>질문과 실패 답변을 개선 로그에 저장할까요?</p>
      {!decision ? (
        <>
          <label>
            <input
              type="checkbox"
              checked={checked}
              onChange={(event) => setChecked(event.target.checked)}
            />
            수집에 동의합니다.
          </label>
          <div className="failure-consent-actions">
            <button type="button" onClick={declineCollection}>비동의</button>
            <button type="button" className="primary" onClick={agreeToCollection} disabled={!checked || isSubmitting}>
              {isSubmitting ? "기록 중" : "동의"}
            </button>
          </div>
        </>
      ) : null}
      {notice ? <span role="status">{notice}</span> : null}
    </section>
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

function LoadingTrace({ activeStep, stepTexts }) {
  const currentStepText = stepTexts?.[activeStep] || stepTexts?.[stepTexts.length - 1] || "질문의 의도와 맥락을 해석하고 있습니다.";
  return (
    <div className="loading-trace" aria-label="실시간 처리 과정" style={{ marginTop: 0, marginBottom: 0 }}>
      <div className="active">
        <p className="loading-step-text" style={{ marginTop: '2px', marginBottom: '2px', display: 'flex', alignItems: 'center' }}>
          <LoadingDots />
          {currentStepText}
        </p>
      </div>
    </div>
  );
}

function LoadingDots() {
  return (
    <span aria-hidden="true" className="loading-dots">
      <span />
      <span />
      <span />
    </span>
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
  if (status === "ok" || status === "latest_news") return false;
  
  const failureStatuses = new Set([
    "error",
    "missing_data",
    "no_data",
    "needs_latest_disclosure",
    "missing_config",
  ]);
  if (failureStatuses.has(status)) return true;

  const normalized = String(answer || "").replace(/\s+/g, " ");
  if (normalized.includes("KDI") || normalized.includes("경제동향보고회") || normalized.includes("출처:")) {
    return false;
  }

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

function buildExampleCompanies(suggestedCompanies) {
  const candidates = Array.isArray(suggestedCompanies) ? suggestedCompanies : [];
  return [...new Set(["삼성전자", ...candidates.filter(Boolean)])].slice(0, 3);
}

function shouldShowAlternativeQuestions(answer, data) {
  const status = data?.calculation?.status || data?.status;
  if (status === "ok") return false;

  const normalized = String(answer || "").replace(/\s+/g, " ").toLowerCase();
  if (normalized.includes("load failed")) return true;
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

function hasKoreanFinalConsonant(text) {
  const value = String(text || "").trim();
  if (["S-Oil", "S-OIL"].includes(value)) return true;

  for (const character of [...value].reverse()) {
    const code = character.charCodeAt(0);
    if (code >= 0xac00 && code <= 0xd7a3) return (code - 0xac00) % 28 !== 0;
  }
  return false;
}

function withKoreanParticle(text, consonantParticle, vowelParticle) {
  return `${text}${hasKoreanFinalConsonant(text) ? consonantParticle : vowelParticle}`;
}

function buildAlternativeQuestions(question) {
  const companyNames = extractCompanies(question);
  const metric = extractMetric(question);
  const contextKeyword = extractContextKeyword(question, metric);

  if (companyNames.length === 0 && isFinancialConceptQuestion(question)) {
    return filterAlternativeQuestions(question, [
      `${metric}과 당기순이익의 차이를 설명해줘`,
      `${metric}률의 계산 공식과 해석 방법을 알려줘`,
      `재무제표에서 ${metric}을 확인할 때 주의할 점은 무엇입니까?`,
    ]);
  }

  if (companyNames.length >= 2) {
    const first = companyNames[0];
    const second = companyNames[1];
    return filterAlternativeQuestions(question, [
      `${withKoreanParticle(first, "과", "와")} ${second}의 최근 ${contextKeyword} 비교 추이를 분석해줘`,
      `${first}의 최근 ${contextKeyword}과 매출액을 함께 비교해줘`,
    ]);
  }

  if (companyNames.length === 1) {
    const company = companyNames[0];
    if (metric === "PBR") {
      return filterAlternativeQuestions(question, [
        `PBR을 구하는 공식과 해석 방법을 알려줘`,
        `${company}의 PBR 계산에 필요한 주가와 BPS를 확인해줘`,
      ]);
    }
    const isPriceRelated = ["주가", "종가", "가격"].some(term => question.includes(term));
    if (isPriceRelated) {
      return filterAlternativeQuestions(question, [
        `${company}의 최근 주가 변동성 및 최대낙폭(MDD)을 계산해줘`,
        `${company}의 최근 5년 주가를 가지고 다음 주가를 예측해줘`,
        `${company}의 최근 1년 주가 흐름을 차트로 보여줘`,
      ]);
    }
    return filterAlternativeQuestions(question, [
      `${company}의 향후 ${contextKeyword} 전망을 계산해줘`,
      `${company}의 최근 ${contextKeyword}과 매출액을 비교해줘`,
    ]);
  }

  return filterAlternativeQuestions(question, [
    `${contextKeyword}을 계산하는 데 필요한 재무제표 계정은 무엇입니까?`,
    `최근 5개년 ${contextKeyword} 추이 전망을 분석해줘`,
  ]);
}

function filterAlternativeQuestions(originalQuestion, candidates) {
  const originalKey = normalizeQuestionForComparison(originalQuestion);
  const seen = new Set([originalKey]);

  return candidates
    .filter((candidate) => {
      const key = normalizeQuestionForComparison(candidate);
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 2);
}

function normalizeQuestionForComparison(question) {
  return String(question || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[\s?.!,。？！]+/g, "");
}

function isFinancialConceptQuestion(question) {
  const normalized = String(question || "").toLowerCase();
  const conceptTerms = ["무엇", "뭐", "필요한", "계정", "계산 방법", "공식", "산식", "차이", "의미", "정의"];
  const financialTerms = ["영업이익", "매출총이익", "당기순이익", "매출액", "매출총이익률", "영업이익률", "당기순이익률", "자기자본이익률", "총자산이익률", "투하자본수익률"];
  return conceptTerms.some((term) => normalized.includes(term)) && financialTerms.some((term) => normalized.includes(term));
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
    ["매출총이익률", ["매출액총이익률", "매출총이익률", "매출총이익마진"]],
    ["영업이익률", ["매출액영업이익률", "영업이익률", "영업마진"]],
    ["당기순이익률", ["매출액순이익률", "당기순이익률", "순이익률", "순이익마진"]],
    ["자기자본이익률", ["자기자본이익률", "roe"]],
    ["총자산이익률", ["총자산이익률", "roa"]],
    ["투하자본수익률", ["투하자본수익률", "roic", "총자본영업이익률"]],
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
  return match ? match[0] : "주요 재무지표";
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
    const lines = block
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => {
        const displayLine = cleanDisplayLine(line);
        return displayLine && !isDecorativeIconLine(displayLine);
      });
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
  const rawLine = line.trim();
  const displayLine = cleanDisplayLine(rawLine);
  const numberedStep = getNumberedStepMeta(displayLine);
  if (numberedStep) {
    return (
      <p className="answer-step-heading" key={key}>
        <strong>
          <span>{numberedStep.number}.</span> {renderInlineMath(numberedStep.text)}
        </strong>
      </p>
    );
  }
  const heading = getHeadingMeta(rawLine);
  if (heading) {
    return (
      <p className="answer-heading" key={key}>
        <span aria-hidden="true">{heading.icon}</span>
        <strong>{renderInlineMath(heading.text)}</strong>
      </p>
    );
  }
  return <p key={key}>{renderInlineMath(displayLine)}</p>;
}

function getNumberedStepMeta(line) {
  const match = line.trim().match(/^(\d+)[.)]\s+(.+)$/);
  if (!match) return null;
  const text = match[2].replace(/[:：]\s*$/, "").trim();
  const calculationHeadingTokens = [
    "공식", "대입", "계산", "산출", "결과", "해석", "조건", "변수", "자료", "단계",
    "판단", "기준", "의견", "비교", "분석", "전망", "평가", "결정"
  ];
  if (text.length > 32 || !calculationHeadingTokens.some((token) => text.includes(token))) return null;
  return { number: match[1], text };
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
    (plain.length <= 24 && /[:：]$/.test(trimmed)) ||
    (
      plain.length <= 32 &&
      !/[.!?。]$/.test(plain) &&
      /(요약|분포(?:\s*및\s*분석)?|분석|비교|결과|해석|전망|시사점|가정(?:\s*및\s*한계)?|한계|주의사항)$/.test(plain)
    );
  const headingRules = [
    { tokens: ["핵심 요약", "요약"], icon: "✨" },
    { tokens: ["종합 비교", "비교 대상", "비교"], icon: "⚖️" },
    { tokens: ["수익률 분포", "분포 및 분석", "분포", "분석"], icon: "📊" },
    { tokens: ["연도별 추이", "숫자 추이"], icon: "📈" },
    { tokens: ["인사이트"], icon: "💡" },
    { tokens: ["원인", "배경"], icon: "🔎" },
    { tokens: ["뉴스", "시장 반응"], icon: "📰" },
    { tokens: ["계산 요약"], icon: "🧮" },
    { tokens: ["결과", "해석", "전망", "시사점"], icon: "💡" },
    { tokens: ["가정 및 한계", "가정", "한계", "주의사항"], icon: "⚠️" },
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

function buildDynamicChartTitle(chart) {
  if (!chart.datasets || chart.datasets.length === 0) return chart.title || "재무 추이";
  const labels = chart.datasets.map((d) => d.label || "");
  if (labels.length === 1) {
    return `${labels[0]} 추이`;
  }
  const hasRevenue = labels.some((l) => l.includes("매출"));
  const hasOperatingIncome = labels.some((l) => l.includes("영업이익"));
  const hasNetIncome = labels.some((l) => l.includes("순이익") || l.includes("순손실") || l.includes("당기순"));
  if (hasOperatingIncome && !hasRevenue && !hasNetIncome) {
    return "영업이익 추이";
  }
  if (hasRevenue && !hasOperatingIncome && !hasNetIncome) {
    return "매출액 추이";
  }
  if (hasNetIncome && !hasRevenue && !hasOperatingIncome) {
    return "당기순이익 추이";
  }
  if (chart.title && chart.title !== "재무 추이" && chart.title !== "실적 추이") {
    return chart.title;
  }
  return "주요 재무지표 추이";
}

function ChartPanel({ chart, compact = false }) {
  if (!chart) return null;
  if (shouldSplitChartByScale(chart)) {
    return (
      <div className="chart-card-stack" aria-label={`${chart.title || "재무 추이"} 분리 그래프`}>
        {chart.datasets.map((dataset) => (
          <ChartPanel
            key={dataset.key}
            chart={{
              ...chart,
              subtitle: [chart.title?.replace(/ 재무 추이$/, ""), chart.subtitle].filter(Boolean).join(" · "),
              datasets: [dataset],
              range: undefined,
            }}
            compact={compact}
          />
        ))}
      </div>
    );
  }
  const dynamicTitle = buildDynamicChartTitle(chart);
  return (
    <section className={`chart-card${compact ? " compact" : ""}`}>
      <div className="chart-title">
        <strong>{dynamicTitle}</strong>
        {chart.subtitle ? <span>{chart.subtitle}</span> : null}
      </div>
      {chart.type === "line" ? <LineChart chart={chart} /> : null}
      {chart.type === "bar" ? <BarChart chart={chart} /> : null}
      {chart.type === "compact_metric_bar" ? <CompactMetricBarChart chart={chart} /> : null}
      {chart.table ? <ChartDataTable table={chart.table} /> : null}
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
  const option = useMemo(() => {
    const colors = ["#FF530A", "#E59A2F", "#A63A00", "#D95C2B"];
    const labels = [...new Map(
      chart.datasets.flatMap((dataset) => dataset.points.map((point) => [String(point.x), point.label || String(point.x)]))
    ).values()];
    const initialVisiblePercent = getInitialLineChartVisiblePercent(labels.length);
    const hasInitialZoom = initialVisiblePercent < 100;
    const zoomStart = 100 - initialVisiblePercent;
    const isForecastChart = chart.datasets.some((dataset) => dataset.forecast);
    const hasDualAxis = Boolean(chart.dual_axis);
    const baseYAxis = {
      type: "value",
      scale: true,
      splitNumber: 4,
      axisTick: { show: false },
      axisLabel: { color: "#796b63", fontSize: 10, formatter: (value) => formatChartValue(Number(value), chart.unit) },
    };
    return {
      animationDuration: 650,
      animationEasing: "cubicOut",
      color: colors,
      aria: { enabled: true, decal: { show: false } },
      grid: { top: isForecastChart ? 72 : chart.datasets.length > 1 ? 54 : 30, right: hasDualAxis ? 82 : 34, bottom: hasInitialZoom ? 58 : 34, left: 72, containLabel: false },
      legend: chart.datasets.length > 1 ? {
        top: 4,
        right: 8,
        itemWidth: 18,
        itemHeight: 3,
        textStyle: { color: "#6f625b", fontSize: 11 },
      } : { show: false },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(255,255,255,0.97)",
        borderColor: "#e1d4ca",
        borderWidth: 1,
        padding: [9, 11],
        textStyle: { color: "#27323a", fontSize: 12 },
        extraCssText: "box-shadow:0 10px 28px rgba(74,47,32,.14);border-radius:8px;",
        formatter: (params) => {
          const rows = Array.isArray(params) ? params : [params];
          const heading = rows[0]?.axisValueLabel || "";
          return [heading, ...rows.map((item) => {
            const rawValue = Array.isArray(item.value) ? item.value.at(-1) : item.value;
            return `${item.marker}${item.seriesName}: <b>${item.data?.display || formatChartValue(Number(rawValue), chart.unit)}</b>`;
          })].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        boundaryGap: false,
        axisLine: { lineStyle: { color: "#d8cec5" } },
        axisTick: { show: false },
        axisLabel: { color: "#796b63", fontSize: 10, hideOverlap: true },
      },
      yAxis: hasDualAxis ? [
        {
          ...baseYAxis,
          name: "매출액",
          position: "left",
          axisLine: { show: true, lineStyle: { color: "#FF530A" } },
          splitLine: { lineStyle: { color: "#eee6df", type: "dashed" } },
        },
        {
          ...baseYAxis,
          name: "영업이익 · 당기순이익",
          position: "right",
          min: (range) => Math.min(0, range.min),
          max: (range) => Math.max(0, range.max),
          axisLine: { show: true, lineStyle: { color: "#E59A2F" } },
          splitLine: { show: false },
        },
      ] : {
        ...baseYAxis,
        axisLine: { show: true, lineStyle: { color: "#d8cec5" } },
        splitLine: { lineStyle: { color: "#eee6df", type: "dashed" } },
      },
      dataZoom: hasInitialZoom ? [
        { type: "inside", start: zoomStart, end: 100 },
        { type: "slider", start: zoomStart, end: 100, height: 14, bottom: 4, borderColor: "transparent", fillerColor: "rgba(208,74,2,.12)" },
      ] : [],
      series: chart.datasets.map((dataset, index) => {
        const seriesColor = dataset.color || colors[index % colors.length];
        const maxPoint = dataset.points.reduce((max, point) => Number(point.y) > Number(max.y) ? point : max, dataset.points[0]);
        const highlightedPoint = dataset.forecast ? dataset.points.at(-1) : maxPoint;
        const highlightedPointIndex = dataset.points.indexOf(highlightedPoint);
        const highlightedLabelPosition = highlightedPointIndex === 0 ? "right" : highlightedPointIndex === dataset.points.length - 1 ? "left" : "top";
        const showHighlightedLabel = !dataset.forecast || dataset.key === "base_forecast";
        return {
          name: dataset.label,
          type: "line",
          yAxisIndex: hasDualAxis && dataset.axis === "profit" ? 1 : 0,
          smooth: dataset.points.length < 80 ? 0.28 : false,
          showSymbol: dataset.points.length <= 60,
          symbol: "circle",
          symbolSize: dataset.points.length > 40 ? 4 : 7,
          lineStyle: { color: seriesColor, width: 3, type: dataset.forecast ? "dashed" : "solid" },
          itemStyle: { color: "#ffffff", borderColor: seriesColor, borderWidth: 2 },
          emphasis: { focus: "series", lineStyle: { width: 4 } },
          data: dataset.points.map((point) => ({ value: [point.label || String(point.x), Number(point.y)], display: point.display, name: point.label })),
          markPoint: highlightedPoint ? {
            symbol: "circle",
            symbolSize: 11,
            itemStyle: { color: "#ffffff", borderColor: seriesColor, borderWidth: 3 },
            label: { show: showHighlightedLabel, position: highlightedLabelPosition, distance: 8, color: "#27323a", fontSize: 10, fontWeight: 700, formatter: highlightedPoint.display },
            data: [{ coord: [highlightedPoint.label || String(highlightedPoint.x), Number(highlightedPoint.y)], value: Number(highlightedPoint.y), name: dataset.forecast ? "전망" : "최댓값" }],
          } : undefined,
        };
      }),
    };
  }, [chart]);
  return <EChart option={option} ariaLabel={chart.title || "재무 추이 선 그래프"} />;
}

function getInitialLineChartVisiblePercent(pointCount) {
  if (pointCount < 10) return 100;
  if (pointCount < 20) return 80;
  if (pointCount < 40) return 70;
  if (pointCount < 80) return 60;
  return 50;
}

function ChartDataTable({ table }) {
  return (
    <div className="chart-data-table-wrap">
      {table.caption ? <strong className="chart-data-table-caption">{table.caption}</strong> : null}
      <table className={`chart-data-table${table.layout === "balanced" ? " balanced" : ""}`}>
        <thead>
          <tr>{table.headers.map((header) => <th key={header}>{header}</th>)}</tr>
        </thead>
        <tbody>
          {table.rows.map((row, rowIndex) => (
            <tr key={`${row[0]}-${rowIndex}`}>
              {row.map((cell, cellIndex) => <td key={`${cellIndex}-${cell}`}>{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function shouldSplitChartByScale(chart) {
  if (chart.type !== "line") return false;
  if (chart.dual_axis) return false;
  if (chart.preserve_combined_scale) return false;
  if (chart.unit !== "KRW" || chart.datasets.length < 2) return false;
  const maxima = chart.datasets
    .map((dataset) => Math.max(...dataset.points.map((point) => Math.abs(Number(point.y)))))
    .filter((value) => Number.isFinite(value) && value > 0);
  if (maxima.length < 2) return false;
  return Math.max(...maxima) / Math.min(...maxima) >= 4;
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

function buildBarColorPalette(count) {
  const size = Math.max(1, count);
  if (size === 1) return ["#FF530A"];
  if (size === 2) return ["#FF530A", "#E59A2F"];
  const start = [0xFD, 0xF0, 0xE6];
  const end = [0xFF, 0x53, 0x0A];
  return Array.from({ length: size }, (_, index) => {
    const ratio = index / (size - 1);
    const rgb = start.map((channel, channelIndex) => Math.round(channel + (end[channelIndex] - channel) * ratio));
    return `#${rgb.map((channel) => channel.toString(16).padStart(2, "0")).join("").toUpperCase()}`;
  });
}

function BarChart({ chart }) {
  const option = useMemo(() => {
    const colors = buildBarColorPalette(chart.bars.length);
    return {
    animationDuration: 650,
    animationEasing: "cubicOut",
    aria: { enabled: true },
    grid: { top: 12, right: 70, bottom: 28, left: 106 },
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(255,255,255,0.97)",
      borderColor: "#e1d4ca",
      textStyle: { color: "#27323a", fontSize: 12 },
      formatter: (params) => `${params.name}: <b>${params.data?.display || formatChartValue(Number(params.value), chart.unit)}</b>`,
    },
    xAxis: {
      type: "value",
      axisLabel: { color: "#796b63", fontSize: 10, formatter: (value) => formatChartValue(Number(value), chart.unit) },
      splitLine: { lineStyle: { color: "#eee6df", type: "dashed" } },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: chart.bars.map((bar) => bar.label),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#4f4540", fontSize: 11, width: 96, overflow: "truncate" },
    },
    series: [{
      type: "bar",
      barMaxWidth: 24,
      data: chart.bars.map((bar, index) => ({
        value: Number(bar.value),
        display: bar.display,
        itemStyle: { color: bar.color || colors[index], borderRadius: Number(bar.value) < 0 ? [6, 0, 0, 6] : [0, 6, 6, 0] },
        label: { show: true, position: Number(bar.value) < 0 ? "left" : "right", color: "#27323a", fontSize: 10, fontWeight: 700, formatter: bar.display },
      })),
    }],
    };
  }, [chart]);
  return <EChart option={option} ariaLabel={chart.title || "재무 비교 막대그래프"} height={Math.max(230, chart.bars.length * 42)} />;
}

function CompactMetricBarChart({ chart }) {
  const shouldStackMetrics = chart.metrics.length > 1 && chart.metrics.some((metric) => (
    metric.values.length > 4
    || metric.values.some((item) => String(item.label || "").length > 9)
  ));
  const chartHeight = shouldStackMetrics ? chart.metrics.length * 240 + 12 : 290;
  const option = useMemo(() => {
    const metricCount = Math.max(1, chart.metrics.length);
    const colors = buildFinancialMetricColorPalette(metricCount);
    const gap = metricCount === 1 ? 0 : 4;
    const gridWidth = (92 - gap * (metricCount - 1)) / metricCount;
    const grids = chart.metrics.map((_, index) => shouldStackMetrics
      ? {
          left: 72,
          right: 24,
          top: 20 + index * 240,
          height: 150,
          containLabel: false,
        }
      : {
          left: `${4 + index * (gridWidth + gap)}%`,
          width: `${gridWidth}%`,
          top: 20,
          bottom: 58,
        });
    const xAxes = chart.metrics.map((metric, index) => ({
      type: "category",
      gridIndex: index,
      data: metric.values.map((item) => item.label || `${item.year}년`),
      name: metric.label,
      nameLocation: "middle",
      nameGap: 30,
      nameTextStyle: { color: "#27323a", fontSize: 12, fontWeight: 700 },
      axisLine: { lineStyle: { color: "#d8cec5" } },
      axisTick: { show: false },
      axisLabel: {
        color: "#6f625b",
        fontSize: 10,
        interval: 0,
        lineHeight: 14,
        width: shouldStackMetrics ? 72 : undefined,
        overflow: shouldStackMetrics ? "break" : "truncate",
      },
    }));
    const yAxes = chart.metrics.map((_, index) => ({
      type: "value",
      gridIndex: index,
      min: (range) => Math.min(0, range.min),
      max: (range) => Math.max(0, range.max),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#796b63", fontSize: 9, formatter: (value) => formatChartValue(Number(value), chart.unit) },
      splitLine: { lineStyle: { color: "#eee6df", type: "dashed" } },
    }));
    return {
      animationDuration: 650,
      aria: { enabled: true },
      grid: grids,
      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(255,255,255,.97)",
        borderColor: "#e1d4ca",
        textStyle: { color: "#27323a", fontSize: 12 },
        formatter: (params) => `${params.name}<br/>${params.marker}${params.seriesName}: <b>${params.data.display}</b>`,
      },
      xAxis: xAxes,
      yAxis: yAxes,
      series: chart.metrics.map((metric, index) => ({
        name: metric.label,
        type: "bar",
        xAxisIndex: index,
        yAxisIndex: index,
        barMaxWidth: 34,
        data: metric.values.map((item) => ({
          value: item.value,
          display: item.display,
          itemStyle: {
            color: colors[index % colors.length],
            opacity: 1,
            borderRadius: Number(item.value) < 0 ? [0, 0, 6, 6] : [6, 6, 0, 0],
          },
          label: {
            show: true,
            position: Number(item.value) < 0 ? "bottom" : "top",
            color: "#27323a",
            fontSize: 9,
            fontWeight: 700,
            formatter: item.display,
          },
        })),
      })),
    };
  }, [chart, shouldStackMetrics]);
  return <EChart option={option} ariaLabel={chart.title || "소규모 재무 데이터 막대그래프"} height={chartHeight} />;
}

function buildFinancialMetricColorPalette(count) {
  const size = Math.max(1, count);
  if (size === 1) return ["#E59A2F"];
  if (size === 2) return ["#E59A2F", "#FF530A"];
  if (size === 3) return ["#E59A2F", "#FEA278", "#FF530A"];
  return buildBarColorPalette(size);
}

function EChart({ option, ariaLabel, height = 280 }) {
  const containerRef = useRef(null);
  const instanceRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const instance = echarts.init(containerRef.current, null, { renderer: "svg" });
    instanceRef.current = instance;

    const doResize = () => {
      if (instanceRef.current) {
        instanceRef.current.resize();
      }
    };

    const observer = new ResizeObserver(() => {
      requestAnimationFrame(doResize);
    });
    observer.observe(containerRef.current);

    const timer = setTimeout(() => {
      doResize();
    }, 100);

    return () => {
      clearTimeout(timer);
      observer.disconnect();
      instance.dispose();
      instanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (instanceRef.current) {
      instanceRef.current.setOption(option, { notMerge: true });
      requestAnimationFrame(() => {
        instanceRef.current?.resize();
      });
    }
  }, [option]);

  return <div ref={containerRef} className="echart" style={{ height }} role="img" aria-label={ariaLabel} />;
}
