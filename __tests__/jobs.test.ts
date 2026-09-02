import { describe, expect, it } from "vitest";
import { isValidJobId } from "@/lib/jobs";

describe("isValidJobId", () => {
  it("aceita UUID v4", () => {
    expect(isValidJobId("da7109d5-8d05-459b-8c41-6cbe2c582bec")).toBe(true);
  });

  it("rejeita path traversal e lixo", () => {
    expect(isValidJobId("../etc/passwd")).toBe(false);
    expect(isValidJobId("..")).toBe(false);
    expect(isValidJobId("da7109d5")).toBe(false);
    expect(isValidJobId("")).toBe(false);
  });
});
