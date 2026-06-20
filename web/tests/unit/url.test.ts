import { describe, it, expect } from "vitest";
import { safeHttpUrl } from "../../src/lib/url.js";

describe("safeHttpUrl", () => {
  it("accepts https URLs", () => {
    expect(safeHttpUrl("https://x")).not.toBeNull();
    expect(safeHttpUrl("https://example.com/path?q=1")).not.toBeNull();
  });

  it("accepts http URLs", () => {
    expect(safeHttpUrl("http://x")).not.toBeNull();
    expect(safeHttpUrl("http://example.com/path")).not.toBeNull();
  });

  it("rejects javascript: URI (XSS vector)", () => {
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull();
  });

  it("rejects data: URI", () => {
    expect(safeHttpUrl("data:text/html,<h1>xss</h1>")).toBeNull();
  });

  it("rejects non-URL strings", () => {
    expect(safeHttpUrl("not a url")).toBeNull();
  });

  it("rejects empty string", () => {
    expect(safeHttpUrl("")).toBeNull();
  });

  it("rejects ftp: URI", () => {
    expect(safeHttpUrl("ftp://example.com")).toBeNull();
  });
});
