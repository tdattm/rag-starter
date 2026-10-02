export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Yêu cầu thất bại (${response.status}).`,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const jsonRequest = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export async function streamChat(
  path: string,
  body: unknown,
  signal: AbortSignal,
  onEvent: (event: string, data: unknown) => void,
) {
  const response = await fetch(`/api${path}`, { ...jsonRequest(body), signal });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "Không thể gửi câu hỏi.",
    );
  }
  if (!response.body) throw new Error("Trình duyệt không hỗ trợ streaming.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "",
    completed = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = block
          .split("\n")
          .find((line) => line.startsWith("event: "))
          ?.slice(7);
        const payload = block
          .split("\n")
          .find((line) => line.startsWith("data: "))
          ?.slice(6);
        if (event && payload) {
          const data = JSON.parse(payload);
          onEvent(event, data);
          if (event === "error") throw new Error(data.message);
          if (event === "done") completed = true;
        }
      }
      if (done) break;
    }
    if (!completed)
      throw new Error("Kết nối bị gián đoạn. Bạn có thể gửi lại câu hỏi.");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
