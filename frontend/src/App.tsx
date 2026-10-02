import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUp,
  BookOpen,
  Check,
  ChevronDown,
  Copy,
  Download,
  FileText,
  Layers3,
  Menu,
  MessageSquare,
  MoreHorizontal,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  Trash2,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, jsonRequest, streamChat } from "./api";
import Library from "./Library";
import Modal from "./Modal";
import type {
  Conversation,
  Document,
  Message,
  Preferences,
  Source,
  Status,
} from "./types";

type View = "chat" | "library" | "search";
const defaults: Preferences = { top_k: 4, min_score: 0.3, temperature: 0.2 };
function readPreferences(): Preferences {
  try {
    const p = JSON.parse(localStorage.getItem("atlas-preferences") || "{}");
    return {
      top_k:
        Number.isInteger(p.top_k) && p.top_k >= 1 && p.top_k <= 8 ? p.top_k : 4,
      min_score:
        typeof p.min_score === "number" && p.min_score >= 0 && p.min_score <= 1
          ? p.min_score
          : 0.3,
      temperature:
        typeof p.temperature === "number" &&
        p.temperature >= 0 &&
        p.temperature <= 1
          ? p.temperature
          : 0.2,
    };
  } catch {
    return defaults;
  }
}

export default function App() {
  const [view, setView] = useState<View>("chat");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string[]>([]);
  const [preferences, setPreferences] = useState<Preferences>(readPreferences);
  const [settings, setSettings] = useState(false);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [source, setSource] = useState<Source | null>(null);
  const [toast, setToast] = useState("");
  const [copied, setCopied] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [results, setResults] = useState<Source[] | null>(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchTime, setSearchTime] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const nearBottom = useRef(true);

  const notify = (message: string) => setToast(message);
  async function refreshDocuments() {
    const docs = await api<Document[]>("/documents");
    setDocuments(docs);
    setSelected((previous) =>
      previous.filter((id) => docs.some((doc) => doc.id === id)),
    );
  }
  async function refreshConversations() {
    setConversations(await api<Conversation[]>("/conversations"));
  }

  useEffect(() => {
    let active = true;
    Promise.all([
      api<Document[]>("/documents"),
      api<Conversation[]>("/conversations"),
    ])
      .then(([docs, chats]) => {
        if (active) {
          setDocuments(docs);
          setConversations(chats);
        }
      })
      .catch((error) => {
        if (active) notify(`Không kết nối được máy chủ: ${error.message}`);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    const refreshStatus = () => {
      api<Status>("/status")
        .then((value) => {
          if (active) setStatus(value);
        })
        .catch(() => {
          if (active) setStatus(null);
        });
    };
    refreshStatus();
    const timer = setInterval(refreshStatus, 15000);
    return () => {
      active = false;
      clearInterval(timer);
      controller.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 6500);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    if (nearBottom.current)
      end.current?.scrollIntoView({
        behavior: busy ? "instant" : "smooth",
        block: "end",
      });
  }, [messages, busy]);
  useEffect(() => {
    try {
      localStorage.setItem("atlas-preferences", JSON.stringify(preferences));
    } catch {
      /* Preferences still work in memory. */
    }
  }, [preferences]);
  useEffect(() => {
    if (textarea.current) {
      textarea.current.style.height = "auto";
      textarea.current.style.height = `${Math.min(textarea.current.scrollHeight, 160)}px`;
    }
  }, [question]);

  function navigate(next: View) {
    setView(next);
    setMobileMenu(false);
  }
  function newChat() {
    if (busy) return;
    setCurrent(null);
    setMessages([]);
    setQuestion("");
    nearBottom.current = true;
    navigate("chat");
  }
  async function openChat(id: string) {
    if (busy) return;
    try {
      const chat = await api<Conversation>(`/conversations/${id}`);
      setCurrent(id);
      setMessages(chat.messages || []);
      nearBottom.current = true;
      navigate("chat");
    } catch (error) {
      notify((error as Error).message);
    }
  }
  async function deleteChat(id: string) {
    if (!window.confirm("Xóa cuộc trò chuyện này?")) return;
    try {
      await api(`/conversations/${id}`, { method: "DELETE" });
      if (current === id) newChat();
      await refreshConversations();
    } catch (error) {
      notify((error as Error).message);
    }
  }
  async function send(text = question) {
    if (!text.trim() || busy || loading) return;
    const prompt = text.trim();
    setQuestion("");
    setBusy(true);
    nearBottom.current = true;
    const abort = new AbortController();
    controller.current = abort;
    const assistantId = crypto.randomUUID();
    let chatId = current;
    let content = "";
    let sources: Source[] = [];
    let outcome: Message["status"] = "complete";
    try {
      if (!chatId) {
        const chat = await api<Conversation>("/conversations", {
          method: "POST",
        });
        chatId = chat.id;
        setCurrent(chat.id);
      }
      setMessages((previous) => [
        ...previous,
        {
          id: crypto.randomUUID(),
          role: "user",
          content: prompt,
          sources: [],
          status: "complete",
        },
        {
          id: assistantId,
          role: "assistant",
          content: "",
          sources: [],
          status: "complete",
        },
      ]);
      await streamChat(
        `/conversations/${chatId}/chat`,
        { query: prompt, document_ids: selected, ...preferences },
        abort.signal,
        (event, data) => {
          if (event === "sources") sources = data as Source[];
          if (event === "token")
            content += (data as { content: string }).content;
          setMessages((previous) =>
            previous.map((message) =>
              message.id === assistantId
                ? { ...message, content, sources }
                : message,
            ),
          );
        },
      );
    } catch (error) {
      outcome = abort.signal.aborted ? "interrupted" : "error";
      if (!abort.signal.aborted) notify((error as Error).message);
      setMessages((previous) =>
        previous.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content:
                  content ||
                  (abort.signal.aborted
                    ? "Câu trả lời đã dừng."
                    : (error as Error).message),
                status: outcome,
              }
            : message,
        ),
      );
    } finally {
      if (outcome === "complete" && chatId) {
        try {
          const chat = await api<Conversation>(`/conversations/${chatId}`);
          setMessages(chat.messages || []);
        } catch {
          /* Preserve the streamed answer if a refresh fails. */
        }
      }
      setBusy(false);
      controller.current = null;
      await refreshConversations().catch(() => {});
      textarea.current?.focus();
    }
  }
  async function performSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim() || searchBusy) return;
    setSearchBusy(true);
    try {
      const data = await api<{ results: Source[]; duration_ms: number }>(
        "/search",
        jsonRequest({
          query: searchQuery,
          document_ids: selected,
          top_k: preferences.top_k,
          min_score: preferences.min_score,
        }),
      );
      setResults(data.results);
      setSearchTime(data.duration_ms);
    } catch (error) {
      notify((error as Error).message);
    } finally {
      setSearchBusy(false);
    }
  }
  function toggleDoc(id: string) {
    setSelected((previous) =>
      previous.includes(id)
        ? previous.filter((item) => item !== id)
        : [...previous, id],
    );
  }
  const ready = status?.llm_ready && status?.embedding_ready;
  const title =
    conversations.find((chat) => chat.id === current)?.title ||
    "Cuộc trò chuyện mới";
  const scope = (
    <details className="scope-selector">
      <summary>
        <Layers3 size={15} />
        {selected.length ? `${selected.length} tài liệu` : "Tất cả tài liệu"}
        <ChevronDown size={14} />
      </summary>
      <div className="scope-menu">
        <button onClick={() => setSelected([])}>
          Dùng toàn bộ thư viện {selected.length === 0 && <Check size={15} />}
        </button>
        {documents.map((doc) => (
          <label key={doc.id}>
            <input
              type="checkbox"
              checked={selected.includes(doc.id)}
              onChange={() => toggleDoc(doc.id)}
            />
            <span>{doc.name}</span>
          </label>
        ))}
        {!documents.length && <p>Thư viện chưa có tài liệu.</p>}
      </div>
    </details>
  );

  return (
    <div className="app-shell">
      {mobileMenu && (
        <button
          className="sidebar-backdrop"
          aria-label="Đóng menu"
          onClick={() => setMobileMenu(false)}
        />
      )}
      <aside className={`sidebar ${mobileMenu ? "open" : ""}`}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            newChat();
          }}
        >
          <span className="brand-mark">
            A<span />
          </span>
          <span>
            atlas<span className="brand-period">.</span>
          </span>
          <span className="brand-label">WORKSPACE</span>
        </a>
        <button className="new-chat" onClick={newChat} disabled={busy}>
          <Plus size={18} />
          <span>Cuộc trò chuyện mới</span>
          <span className="key-hint">↗</span>
        </button>
        <div className="nav-label">KHÔNG GIAN LÀM VIỆC</div>
        <nav aria-label="Điều hướng chính">
          <button
            className={view === "chat" ? "active" : ""}
            onClick={() => navigate("chat")}
          >
            <MessageSquare size={18} />
            Trò chuyện
            <span className="nav-active-dot" />
          </button>
          <button
            aria-label="Thư viện"
            className={view === "library" ? "active" : ""}
            onClick={() => navigate("library")}
          >
            <BookOpen size={18} />
            Thư viện<span className="nav-count">{documents.length}</span>
          </button>
          <button
            className={view === "search" ? "active" : ""}
            onClick={() => navigate("search")}
          >
            <Search size={18} />
            Tìm kiếm
          </button>
        </nav>
        <div className="history-heading">
          <span className="nav-label">GẦN ĐÂY</span>
          <MessageSquare size={13} />
        </div>
        <div className="history-list">
          {conversations.map((chat) => (
            <div
              className={`history-item ${current === chat.id ? "selected" : ""}`}
              key={chat.id}
            >
              <button onClick={() => void openChat(chat.id)} disabled={busy}>
                <span className="history-dot" />
                {chat.title}
              </button>
              <button
                className="history-delete"
                aria-label={`Xóa cuộc trò chuyện ${chat.title}`}
                onClick={() => void deleteChat(chat.id)}
                disabled={busy}
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
          {!conversations.length && (
            <p className="history-empty">
              Những ý tưởng của bạn
              <br />
              sẽ được lưu tại đây.
            </p>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="local-card">
            <span className="local-icon">
              <ShieldCheck size={18} />
            </span>
            <div>
              <strong>Không gian riêng tư</strong>
              <span>AI chạy trên máy của bạn</span>
            </div>
            <span className="small-dot" />
          </div>
          <button className="settings-button" onClick={() => setSettings(true)}>
            <Settings2 size={17} />
            Tùy chỉnh không gian
            <MoreHorizontal size={17} />
          </button>
          <div className="profile">
            <span className="avatar">ME</span>
            <div>
              <strong>Không gian cá nhân</strong>
              <span>Local workspace</span>
            </div>
            <span className="version">v1.0</span>
          </div>
        </div>
      </aside>
      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-toggle"
              aria-label="Mở menu"
              onClick={() => setMobileMenu(true)}
            >
              <Menu size={20} />
            </button>
            <span>Không gian cá nhân</span>
            <span className="slash">/</span>
            <strong>
              {view === "chat"
                ? "Trò chuyện"
                : view === "library"
                  ? "Thư viện"
                  : "Tìm kiếm"}
            </strong>
          </div>
          <button
            className={`model-pill ${ready ? "online" : ""}`}
            onClick={() => setSettings(true)}
          >
            <i />
            <span>
              {ready
                ? "Qwen2.5 · 3B"
                : status?.connected
                  ? "Đang chờ model"
                  : "Chưa kết nối Ollama"}
            </span>
            <ChevronDown size={13} />
          </button>
        </header>
        {loading ? (
          <div className="loading-workspace">
            <span className="loader" />
            <p>Đang mở không gian của bạn…</p>
          </div>
        ) : view === "library" ? (
          <Library
            documents={documents}
            maxMB={status?.max_upload_mb || 10}
            refresh={refreshDocuments}
            notify={notify}
            onChat={(id) => {
              newChat();
              setSelected([id]);
            }}
          />
        ) : view === "search" ? (
          <div className="page search-page">
            <div className="eyebrow">TÌM HIỂU SÂU HƠN</div>
            <h1>
              Tìm điều bạn cần<span>.</span>
            </h1>
            <p className="page-description">
              Khám phá các đoạn nguồn bằng ngữ nghĩa và từ khóa.
            </p>
            <form
              className="search-form"
              onSubmit={(e) => void performSearch(e)}
            >
              <Search size={21} />
              <input
                aria-label="Tìm kiếm tài liệu"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Bạn đang tìm thông tin gì?"
                maxLength={2000}
              />
              <button
                className="button primary"
                disabled={searchBusy || !searchQuery.trim()}
              >
                {searchBusy ? "Đang tìm…" : "Tìm kiếm"}
                <ArrowRight size={16} />
              </button>
            </form>
            <div className="search-meta">
              {scope}
              <span>
                {results
                  ? `${results.length} đoạn nguồn · ${(searchTime / 1000).toFixed(1)} giây`
                  : "Ngữ nghĩa + từ khóa"}
              </span>
            </div>
            {results === null ? (
              <div className="search-empty">
                <div className="search-art">
                  <Search size={36} />
                  <span />
                  <span />
                </div>
                <h3>Đôi khi, câu trả lời nằm trong một đoạn nhỏ.</h3>
                <p>
                  Tìm một khái niệm, thuật ngữ hoặc ý tưởng trong thư viện của
                  bạn.
                </p>
              </div>
            ) : !results.length ? (
              <div className="empty-small">
                <Search size={30} />
                <h3>Chưa tìm thấy đoạn phù hợp</h3>
                <p>Thử từ khóa khác, điều chỉnh phạm vi hoặc thêm tài liệu.</p>
              </div>
            ) : (
              <div className="search-results">
                {results.map((item) => (
                  <button
                    className="search-result"
                    key={item.id}
                    onClick={() => setSource(item)}
                  >
                    <div>
                      <span className="source-number">
                        {item.citation.toString().padStart(2, "0")}
                      </span>
                      <FileText size={15} />
                      <strong>{item.name}</strong>
                      <span className="score">
                        Cosine {item.score.toFixed(2)}
                      </span>
                    </div>
                    <p>{item.text}</p>
                    <span className="result-footer">
                      {item.page ? `Trang ${item.page} · ` : ""}Xem đoạn nguồn
                      <ArrowUp size={14} />
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <>
            {messages.length > 0 && (
              <div className="conversation-toolbar">
                <div>
                  <span className="eyebrow">CUỘC TRÒ CHUYỆN</span>
                  <h2>{title}</h2>
                </div>
                {current && (
                  <a
                    className="button secondary compact"
                    href={`/api/conversations/${current}/export`}
                    download
                  >
                    <Download size={15} />
                    <span>Xuất hội thoại</span>
                  </a>
                )}
              </div>
            )}
            <div
              className={`chat-scroll ${messages.length === 0 ? "welcome-scroll" : ""}`}
              onScroll={(e) => {
                const el = e.currentTarget;
                nearBottom.current =
                  el.scrollHeight - el.scrollTop - el.clientHeight < 120;
              }}
            >
              {messages.length === 0 ? (
                <div className="welcome">
                  <div className="welcome-badge">
                    <span className="small-dot" /> TRI THỨC CỦA BẠN. KHẢ NĂNG
                    MỚI.
                  </div>
                  <div className="orbit-art" aria-hidden="true">
                    <div className="orbit orbit-one" />
                    <div className="orbit orbit-two" />
                    <div className="orbit orbit-three" />
                    <div className="orbit-core">
                      <Sparkles size={34} strokeWidth={1.3} />
                    </div>
                    <span className="orbit-point p1" />
                    <span className="orbit-point p2" />
                    <span className="orbit-point p3" />
                  </div>
                  <h1>
                    Tài liệu của bạn.
                    <br />
                    <span>Câu trả lời của bạn.</span>
                  </h1>
                  <p>
                    Một nơi để kết nối những điều bạn biết.
                    <br />
                    Đặt câu hỏi, khám phá ý tưởng, luôn có nguồn để đối chiếu.
                  </p>
                  <div className="suggestions">
                    <button
                      onClick={() =>
                        documents.length
                          ? void send(
                              "Tóm tắt những nội dung chính trong tài liệu đã chọn.",
                            )
                          : navigate("library")
                      }
                    >
                      <span className="suggestion-icon">
                        <FileText size={19} />
                      </span>
                      <strong>Từ dài thành ngắn</strong>
                      <span>Tóm tắt những ý chính</span>
                      <ArrowRight size={16} />
                    </button>
                    <button
                      onClick={() =>
                        documents.length
                          ? void send(
                              "Giải thích các khái niệm quan trọng trong tài liệu bằng ngôn ngữ dễ hiểu.",
                            )
                          : navigate("library")
                      }
                    >
                      <span className="suggestion-icon">
                        <Sparkles size={19} />
                      </span>
                      <strong>Hiểu sâu một chút</strong>
                      <span>Giải thích điều còn mơ hồ</span>
                      <ArrowRight size={16} />
                    </button>
                    <button onClick={() => navigate("search")}>
                      <span className="suggestion-icon">
                        <Layers3 size={19} />
                      </span>
                      <strong>Kết nối các ý tưởng</strong>
                      <span>Khám phá trong thư viện</span>
                      <ArrowRight size={16} />
                    </button>
                  </div>
                  {!documents.length && (
                    <button
                      className="onboarding-link"
                      onClick={() => navigate("library")}
                    >
                      <Plus size={15} />
                      Thêm tài liệu đầu tiên để bắt đầu
                      <ArrowRight size={14} />
                    </button>
                  )}
                </div>
              ) : (
                <div className="message-list">
                  {messages.map((message, i) => (
                    <article
                      className={`message ${message.role}`}
                      key={message.id}
                    >
                      <div className={`message-avatar ${message.role}`}>
                        {message.role === "user" ? "B" : <Sparkles size={17} />}
                      </div>
                      <div className="message-body">
                        <div className="message-author">
                          {message.role === "user" ? "Bạn" : "Atlas"}
                          {message.role === "assistant" && (
                            <span>Qwen2.5 · 3B</span>
                          )}
                        </div>
                        <div className="markdown">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              img: () => null,
                              a: ({ children, href }) => {
                                const citation = href?.match(/^#source-(\d+)$/);
                                const matched =
                                  citation &&
                                  message.sources.find(
                                    (item) => item.citation === +citation[1],
                                  );
                                return matched ? (
                                  <button
                                    className="inline-citation"
                                    onClick={() => setSource(matched)}
                                    aria-label={`Xem nguồn ${matched.citation}`}
                                  >
                                    {children}
                                  </button>
                                ) : (
                                  <a
                                    href={href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
                                    {children}
                                  </a>
                                );
                              },
                            }}
                          >
                            {message.content.replace(
                              /\[(\d+)\](?!\()/g,
                              (match, number) =>
                                message.sources.some(
                                  (item) => item.citation === +number,
                                )
                                  ? `[${number}](#source-${number})`
                                  : match,
                            )}
                          </ReactMarkdown>
                          {!message.content &&
                            busy &&
                            i === messages.length - 1 && (
                              <span className="thinking">
                                <i />
                                <i />
                                <i />
                                Đang tìm trong tài liệu…
                              </span>
                            )}
                        </div>
                        {message.status !== "complete" && (
                          <span className="message-state">
                            {message.status === "interrupted"
                              ? "Đã dừng"
                              : "Câu trả lời chưa hoàn tất"}
                          </span>
                        )}
                        {message.sources.length > 0 && (
                          <div className="message-sources">
                            <div className="source-label">
                              <BookOpen size={13} />
                              NGUỒN THAM KHẢO
                            </div>
                            <div className="source-chips">
                              {message.sources.map((item) => (
                                <button
                                  key={item.id}
                                  onClick={() => setSource(item)}
                                >
                                  <span>{item.citation}</span>
                                  <FileText size={12} />
                                  <strong>{item.name}</strong>
                                  {item.page && <small>tr. {item.page}</small>}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                        {message.role === "assistant" && message.content && (
                          <div className="message-actions">
                            <button
                              aria-label="Sao chép câu trả lời"
                              onClick={() => {
                                navigator.clipboard
                                  .writeText(message.content)
                                  .then(() => {
                                    setCopied(message.id);
                                    setTimeout(() => setCopied(""), 2000);
                                  })
                                  .catch(() =>
                                    notify(
                                      "Không thể sao chép trong trình duyệt này.",
                                    ),
                                  );
                              }}
                            >
                              {copied === message.id ? (
                                <Check size={14} />
                              ) : (
                                <Copy size={14} />
                              )}
                              <span>
                                {copied === message.id
                                  ? "Đã sao chép"
                                  : "Sao chép"}
                              </span>
                            </button>
                          </div>
                        )}
                      </div>
                    </article>
                  ))}
                  <div ref={end} />
                </div>
              )}
            </div>
            <div className="composer-area">
              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  void send();
                }}
              >
                <textarea
                  ref={textarea}
                  aria-label="Câu hỏi"
                  placeholder={
                    documents.length
                      ? "Hỏi điều gì đó từ tài liệu của bạn…"
                      : "Thêm tài liệu vào thư viện, rồi đặt câu hỏi…"
                  }
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  maxLength={2000}
                  rows={1}
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      !e.shiftKey &&
                      !e.nativeEvent.isComposing
                    ) {
                      e.preventDefault();
                      void send();
                    }
                  }}
                />
                <div className="composer-bottom">
                  {scope}
                  <div className="composer-right">
                    <span className="enter-hint">
                      ↵ gửi · shift ↵ xuống dòng
                    </span>
                    {busy ? (
                      <button
                        className="send-button stop"
                        type="button"
                        aria-label="Dừng câu trả lời"
                        onClick={() => controller.current?.abort()}
                      >
                        <Square size={15} fill="currentColor" />
                      </button>
                    ) : (
                      <button
                        className="send-button"
                        type="submit"
                        aria-label="Gửi câu hỏi"
                        disabled={!question.trim() || !documents.length}
                      >
                        <ArrowUp size={20} />
                      </button>
                    )}
                  </div>
                </div>
              </form>
              <div className="composer-footnote">
                <ShieldCheck size={12} />
                <span>Chạy cục bộ · Có nguồn trích dẫn</span>
                <span className="footnote-separator">·</span>
                <span>AI có thể mắc lỗi. Hãy đối chiếu nguồn.</span>
              </div>
            </div>
          </>
        )}
        <footer className="workspace-footer">
          <span>ATLAS / PERSONAL KNOWLEDGE</span>
          <span>
            <i className="small-dot" />
            {documents.length} tài liệu ·{" "}
            {documents.reduce((sum, doc) => sum + doc.chunk_count, 0)} đoạn tri
            thức
          </span>
        </footer>
      </main>
      {toast && (
        <div className="toast" role="status">
          <span>{toast}</span>
          <button aria-label="Đóng thông báo" onClick={() => setToast("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {source && (
        <Modal title="Đối chiếu nguồn" onClose={() => setSource(null)} wide>
          <div className="source-detail-heading">
            <span className="source-number">{source.citation}</span>
            <div>
              <h3>{source.name}</h3>
              <p>
                {source.page ? `Trang ${source.page} · ` : ""}Cosine similarity:{" "}
                {source.score.toFixed(3)}
              </p>
            </div>
          </div>
          <div className="source-detail-text">{source.text}</div>
          <p className="muted">
            Đây là đoạn được truy xuất để tạo câu trả lời. Số cosine thể hiện
            mức tương đồng ngữ nghĩa, không phải độ tin cậy của câu trả lời.
          </p>
          {/^https?:\/\//.test(source.source) && (
            <a
              className="button secondary"
              href={source.source}
              target="_blank"
              rel="noopener noreferrer"
            >
              Mở trang gốc
              <ArrowRight size={15} />
            </a>
          )}
        </Modal>
      )}
      {settings && (
        <Modal title="Tùy chỉnh không gian" onClose={() => setSettings(false)}>
          <div className="settings-model">
            <div className="eyebrow">MODEL CỤC BỘ</div>
            <div>
              <span>Ngôn ngữ</span>
              <strong>{status?.llm_model || "qwen2.5:3b"}</strong>
              <span
                className={status?.llm_ready ? "text-green" : "text-yellow"}
              >
                {status?.llm_ready ? "Sẵn sàng" : "Chưa sẵn sàng"}
              </span>
            </div>
            <div>
              <span>Embedding</span>
              <strong>{status?.embedding_model || "bge-m3"}</strong>
              <span
                className={
                  status?.embedding_ready ? "text-green" : "text-yellow"
                }
              >
                {status?.embedding_ready ? "Sẵn sàng" : "Chưa sẵn sàng"}
              </span>
            </div>
            {!ready && (
              <p className="model-help">
                Chờ model tải xong. Kiểm tra tiến trình bằng{" "}
                <code>docker compose logs -f models</code>.
              </p>
            )}
          </div>
          <div className="settings-field">
            <label htmlFor="top-k">
              Số đoạn nguồn <strong>{preferences.top_k}</strong>
            </label>
            <p>
              Nhiều đoạn giúp bao quát hơn nhưng có thể làm chậm câu trả lời.
            </p>
            <input
              id="top-k"
              type="range"
              min="1"
              max="8"
              step="1"
              value={preferences.top_k}
              onChange={(e) =>
                setPreferences((p) => ({ ...p, top_k: +e.target.value }))
              }
            />
          </div>
          <div className="settings-field">
            <label htmlFor="min-score">
              Ngưỡng ngữ nghĩa{" "}
              <strong>{preferences.min_score.toFixed(2)}</strong>
            </label>
            <p>Lọc kết quả ngữ nghĩa yếu. Kết quả khớp từ khóa vẫn được giữ.</p>
            <input
              id="min-score"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={preferences.min_score}
              onChange={(e) =>
                setPreferences((p) => ({ ...p, min_score: +e.target.value }))
              }
            />
          </div>
          <div className="settings-field">
            <label htmlFor="temperature">
              Mức linh hoạt{" "}
              <strong>{preferences.temperature.toFixed(1)}</strong>
            </label>
            <p>Giá trị thấp phù hợp cho câu trả lời bám sát tài liệu.</p>
            <input
              id="temperature"
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={preferences.temperature}
              onChange={(e) =>
                setPreferences((p) => ({ ...p, temperature: +e.target.value }))
              }
            />
          </div>
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setPreferences(defaults)}
            >
              Khôi phục mặc định
            </button>
            <button
              className="button primary"
              onClick={() => setSettings(false)}
            >
              Hoàn tất
              <Check size={16} />
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
