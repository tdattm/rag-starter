import { useRef, useState } from "react";
import {
  ArrowUpRight,
  FileText,
  Globe,
  LoaderCircle,
  Plus,
  Search,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { api, jsonRequest } from "./api";
import Modal from "./Modal";
import type { Document } from "./types";

const bytes = (value: number) =>
  value > 1024 * 1024
    ? `${(value / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(value / 1024))} KB`;

export default function Library({
  documents,
  maxMB,
  refresh,
  notify,
  onChat,
}: {
  documents: Document[];
  maxMB: number;
  refresh: () => Promise<void>;
  notify: (message: string) => void;
  onChat: (id: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState("");
  const [filter, setFilter] = useState("");
  const [drag, setDrag] = useState(false);
  const [url, setURL] = useState("");
  const [urlModal, setURLModal] = useState(false);
  const [preview, setPreview] = useState<Document | null>(null);
  const [chunks, setChunks] = useState<
    { id: string; text: string; page: number | null }[]
  >([]);
  const [previewBusy, setPreviewBusy] = useState(false);

  async function upload(files: FileList | File[]) {
    if (busy) return;
    for (const file of Array.from(files)) {
      if (file.size > maxMB * 1024 * 1024) {
        notify(`${file.name}: tối đa ${maxMB} MB.`);
        continue;
      }
      setBusy(file.name);
      try {
        const form = new FormData();
        form.append("file", file);
        const result = await api<{ duplicate: boolean }>("/documents", {
          method: "POST",
          body: form,
        });
        notify(
          result.duplicate
            ? `${file.name} đã có trong thư viện.`
            : `Đã thêm ${file.name}.`,
        );
        await refresh();
      } catch (error) {
        notify((error as Error).message);
      }
    }
    setBusy("");
    if (input.current) input.current.value = "";
  }

  async function importURL(e: React.FormEvent) {
    e.preventDefault();
    setURLModal(false);
    setBusy("trang web");
    try {
      const result = await api<{ duplicate: boolean }>(
        "/documents/url",
        jsonRequest({ url }),
      );
      notify(
        result.duplicate
          ? "Trang web này đã có trong thư viện."
          : "Đã thêm trang web.",
      );
      setURL("");
      await refresh();
    } catch (error) {
      notify((error as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function remove(doc: Document) {
    if (
      !window.confirm(
        `Xóa “${doc.name}” khỏi thư viện? Hội thoại cũ vẫn giữ đoạn nguồn đã trích.`,
      )
    )
      return;
    try {
      await api(`/documents/${doc.id}`, { method: "DELETE" });
      await refresh();
      notify("Đã xóa tài liệu.");
    } catch (error) {
      notify((error as Error).message);
    }
  }

  async function openPreview(doc: Document) {
    setPreview(doc);
    setChunks([]);
    setPreviewBusy(true);
    try {
      setChunks(await api(`/documents/${doc.id}/chunks`));
    } catch (error) {
      notify((error as Error).message);
      setPreview(null);
    } finally {
      setPreviewBusy(false);
    }
  }

  async function loadMore() {
    if (!preview) return;
    setPreviewBusy(true);
    try {
      const more = await api<typeof chunks>(
        `/documents/${preview.id}/chunks?offset=${chunks.length}`,
      );
      setChunks((previous) => [...previous, ...more]);
    } catch (error) {
      notify((error as Error).message);
    } finally {
      setPreviewBusy(false);
    }
  }

  const filtered = documents.filter((doc) =>
    doc.name.toLocaleLowerCase("vi").includes(filter.toLocaleLowerCase("vi")),
  );
  return (
    <div className="page library-page">
      <div className="eyebrow">KHÔNG GIAN CỦA BẠN</div>
      <div className="page-heading">
        <div>
          <h1>
            Thư viện tri thức<span>.</span>
          </h1>
          <p>
            Mỗi tài liệu là một mảnh ghép. Kết nối chúng để tìm câu trả lời.
          </p>
        </div>
        <button
          className="button secondary"
          onClick={() => setURLModal(true)}
          disabled={!!busy}
        >
          <Globe size={16} /> Nhập từ URL
        </button>
      </div>
      <input
        ref={input}
        type="file"
        className="visually-hidden"
        accept=".pdf,.txt,.md,.json"
        multiple
        onChange={(e) => e.target.files && void upload(e.target.files)}
        aria-label="Chọn tài liệu"
      />
      <button
        className={`upload-zone ${drag ? "drag" : ""}`}
        disabled={!!busy}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          if (!busy) void upload(e.dataTransfer.files);
        }}
      >
        <span className="upload-icon">
          {busy ? (
            <LoaderCircle className="spin" size={25} />
          ) : (
            <UploadCloud size={25} />
          )}
        </span>
        <strong>
          {busy
            ? `Đang tạo chỉ mục cho ${busy}…`
            : "Kéo thả tài liệu của bạn vào đây"}
        </strong>
        <span>
          {busy
            ? "Tài liệu sẽ xuất hiện khi xử lý hoàn tất. Bạn có thể tiếp tục xem thư viện."
            : `hoặc nhấn để chọn tệp · PDF, TXT, MD, JSON · tối đa ${maxMB} MB/tệp`}
        </span>
        {!busy && (
          <span className="upload-choose">
            <Plus size={15} /> Chọn tài liệu
          </span>
        )}
      </button>
      <div className="library-toolbar">
        <h2>
          Tất cả tài liệu <span className="count">{documents.length}</span>
        </h2>
        <label className="input-with-icon">
          <Search size={16} />
          <input
            aria-label="Lọc tài liệu"
            placeholder="Tìm trong thư viện…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </label>
      </div>
      {filtered.length ? (
        <div className="document-list">
          {filtered.map((doc) => (
            <article className="document-row" key={doc.id}>
              <div
                className={`file-icon ${doc.mime === "text/html" ? "web" : ""}`}
              >
                {doc.mime === "text/html" ? (
                  <Globe size={21} />
                ) : (
                  <FileText size={21} />
                )}
              </div>
              <button
                className="document-name"
                onClick={() => void openPreview(doc)}
              >
                <strong>{doc.name}</strong>
                <span>
                  {doc.mime === "text/html"
                    ? doc.source
                    : `${bytes(doc.size)} · ${doc.chunk_count} đoạn`}{" "}
                  · {new Date(doc.created_at).toLocaleDateString("vi-VN")}
                </span>
              </button>
              <span className="ready-tag">
                <i /> Đã lập chỉ mục
              </span>
              <button
                className="icon-button"
                aria-label={`Hỏi về ${doc.name}`}
                title="Hỏi về tài liệu"
                onClick={() => onChat(doc.id)}
              >
                <ArrowUpRight size={18} />
              </button>
              <button
                className="icon-button danger"
                aria-label={`Xóa ${doc.name}`}
                onClick={() => void remove(doc)}
                disabled={!!busy}
              >
                <Trash2 size={17} />
              </button>
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-small">
          <FileText size={32} />
          <h3>
            {filter
              ? "Không tìm thấy tài liệu"
              : "Tri thức bắt đầu từ một tài liệu"}
          </h3>
          <p>
            {filter
              ? "Thử tên khác hoặc xóa bộ lọc."
              : "Thêm ghi chú, bài nghiên cứu hoặc tài liệu học tập để bắt đầu."}
          </p>
        </div>
      )}
      <div className="library-note">
        <span className="small-dot" /> Tài liệu được xử lý trên máy chủ của bạn.
        Không gửi đến dịch vụ AI bên ngoài.
      </div>
      {urlModal && (
        <Modal title="Nhập trang web" onClose={() => setURLModal(false)}>
          <p className="muted">
            Lưu nội dung một trang công khai vào thư viện. Trang cần đăng nhập
            hoặc chạy JavaScript có thể không đọc được.
          </p>
          <form onSubmit={(e) => void importURL(e)}>
            <label className="field-label" htmlFor="url">
              Đường dẫn trang web
            </label>
            <input
              id="url"
              type="url"
              required
              autoFocus
              placeholder="https://example.com/article"
              value={url}
              onChange={(e) => setURL(e.target.value)}
              className="text-input"
            />
            <div className="modal-actions">
              <button
                type="button"
                className="button secondary"
                onClick={() => setURLModal(false)}
              >
                Hủy
              </button>
              <button className="button primary" type="submit">
                <Plus size={16} /> Thêm vào thư viện
              </button>
            </div>
          </form>
        </Modal>
      )}
      {preview && (
        <Modal title={preview.name} onClose={() => setPreview(null)} wide>
          <p className="muted">
            {preview.chunk_count} đoạn đã được lập chỉ mục ·{" "}
            {preview.embedding_model}
          </p>
          <div className="chunk-list">
            {chunks.map((chunk, i) => (
              <article key={chunk.id}>
                <div className="eyebrow">
                  ĐOẠN {i + 1}
                  {chunk.page ? ` · TRANG ${chunk.page}` : ""}
                </div>
                <p>{chunk.text}</p>
              </article>
            ))}
          </div>
          {previewBusy && <p className="muted">Đang tải…</p>}
          {chunks.length < preview.chunk_count && !previewBusy && (
            <button
              className="button secondary"
              onClick={() => void loadMore()}
            >
              Xem thêm đoạn
            </button>
          )}
        </Modal>
      )}
    </div>
  );
}
