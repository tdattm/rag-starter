import { expect, test, type Page } from "@playwright/test";

async function navigate(page: Page, label: string) {
  const menu = page.getByRole("button", { name: "Mở menu", exact: true });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: label, exact: true })
    .click();
}

test("welcome, library, search and settings work without fabricated data", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Tài liệu của bạn. Câu trả lời của bạn.",
    }),
  ).toBeVisible();
  await navigate(page, "Thư viện");
  await expect(
    page.getByRole("heading", { name: "Thư viện tri thức." }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Nhập từ URL" })).toBeVisible();
  await page.getByRole("button", { name: "Nhập từ URL" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await navigate(page, "Tìm kiếm");
  await page
    .getByRole("textbox", { name: "Tìm kiếm tài liệu", exact: true })
    .fill("missing keyword");
  await page
    .getByRole("button", { name: "Tìm kiếm", exact: true })
    .last()
    .click();
  await expect(
    page.getByRole("heading", { name: "Chưa tìm thấy đoạn phù hợp" }),
  ).toBeVisible();
  await page.locator(".model-pill").click();
  await expect(
    page.getByRole("heading", { name: "Tùy chỉnh không gian" }),
  ).toBeVisible();
  await page.locator("#top-k").fill("6");
  await page.getByRole("button", { name: "Hoàn tất" }).click();
  await page.reload();
  await page.locator(".model-pill").click();
  await expect(page.locator("#top-k")).toHaveValue("6");
  await page.getByRole("button", { name: "Khôi phục mặc định" }).click();
  await page.getByRole("button", { name: "Hoàn tất" }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});

test("upload validation and private URL error are visible", async ({
  page,
}) => {
  await page.goto("/");
  await navigate(page, "Thư viện");
  await page.getByLabel("Chọn tài liệu").setInputFiles({
    name: "empty.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(" "),
  });
  await expect(page.getByRole("status")).toContainText("không có văn bản");
  await page.getByRole("button", { name: "Nhập từ URL" }).click();
  await page.getByLabel("Đường dẫn trang web").fill("http://127.0.0.1");
  await page.getByRole("button", { name: "Thêm vào thư viện" }).click();
  await expect(page.getByRole("status")).toContainText("nội bộ");
});
