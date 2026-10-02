import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("upload, source preview, streamed chat, history, export and stop", async ({
  page,
  request,
}, testInfo) => {
  const suffix = `${testInfo.project.name}-${Date.now()}`;
  const name = `atlas-${suffix}.md`;
  const prompt = `Atlas ${suffix} lưu dữ liệu ở đâu?`;
  let documentId: string | undefined;
  let conversationId: string | undefined;
  try {
    await page.goto("/");
    const menu = page.getByRole("button", { name: "Mở menu", exact: true });
    if (await menu.isVisible()) await menu.click();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Thư viện", exact: true })
      .click();
    await page
      .getByLabel("Chọn tài liệu")
      .setInputFiles({
        name,
        mimeType: "text/markdown",
        buffer: Buffer.from(
          `Atlas ${suffix} dùng SQLite để lưu dữ liệu và hội thoại.`,
        ),
      });
    await expect(
      page.locator(".document-name").filter({ hasText: name }),
    ).toBeVisible();
    const documents = await (await request.get("/api/documents")).json();
    documentId = documents.find(
      (doc: { name: string }) => doc.name === name,
    ).id;
    await page.locator(".document-name").filter({ hasText: name }).click();
    await expect(page.getByRole("dialog")).toContainText("SQLite");
    await page.getByRole("button", { name: "Đóng", exact: true }).click();
    await page
      .getByRole("button", { name: `Hỏi về ${name}`, exact: true })
      .click();
    await page
      .getByRole("textbox", { name: "Câu hỏi", exact: true })
      .fill(prompt);
    await page
      .getByRole("button", { name: "Gửi câu hỏi", exact: true })
      .click();
    await expect(page.locator(".message.assistant .markdown")).toContainText(
      "Atlas dùng SQLite",
    );
    await expect(
      page.getByRole("button", { name: "Dừng câu trả lời" }),
    ).not.toBeVisible();
    const conversations = await (
      await request.get("/api/conversations")
    ).json();
    conversationId = conversations.find(
      (chat: { title: string }) => chat.title === prompt,
    ).id;
    await page
      .getByRole("button", { name: "Xem nguồn 1", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toContainText(
      `Atlas ${suffix} dùng SQLite`,
    );
    await page.keyboard.press("Escape");
    const downloadPromise = page.waitForEvent("download");
    await page.locator(".conversation-toolbar a").click();
    const download = await downloadPromise;
    const downloadPath = await download.path();
    expect(await readFile(downloadPath!, "utf-8")).toContain("SQLite");
    await page.reload();
    if (await menu.isVisible()) await menu.click();
    await page
      .locator(".history-item")
      .getByRole("button", { name: prompt, exact: true })
      .click();
    await expect(page.locator(".message.assistant .markdown")).toContainText(
      "SQLite",
    );
    await page
      .getByRole("textbox", { name: "Câu hỏi", exact: true })
      .fill(`Atlas ${suffix} trả lời chậm`);
    await page
      .getByRole("button", { name: "Gửi câu hỏi", exact: true })
      .click();
    await expect(
      page.locator(".message.assistant .markdown").last(),
    ).toContainText("Đang trả lời");
    await page
      .getByRole("button", { name: "Dừng câu trả lời", exact: true })
      .click();
    await expect(page.locator(".message-state").last()).toHaveText("Đã dừng");
    await expect
      .poll(async () => {
        const chat = await (
          await request.get(`/api/conversations/${conversationId}`)
        ).json();
        return chat.messages.at(-1)?.status;
      })
      .toBe("interrupted");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
  } finally {
    if (conversationId)
      await request.delete(`/api/conversations/${conversationId}`);
    if (documentId) await request.delete(`/api/documents/${documentId}`);
  }
});
