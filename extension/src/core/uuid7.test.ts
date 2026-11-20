import { describe, expect, it } from "vitest";

import { uuidV7 } from "./uuid7";

const SHAPE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

// The server takes only a version 7 UUID as a recipe's id, so that ordering
// by id stays ordering by age (#156). The draft makes it when it starts (D8).
describe("uuidV7", () => {
  it("is a version 7 UUID with the RFC 9562 variant", () => {
    expect(uuidV7(Date.UTC(2026, 10, 20), new Uint8Array(10))).toMatch(SHAPE);
  });

  it("starts with the time in milliseconds", () => {
    const id = uuidV7(0x01a1f5b5dbe2, new Uint8Array(10).fill(0xff));

    expect(id.startsWith("01a1f5b5-dbe2-7")).toBe(true);
    expect(id).toMatch(SHAPE);
  });

  it("puts the random bytes in the rest", () => {
    const random = Uint8Array.from([
      0x0a, 0xbc, 0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0,
    ]);

    expect(uuidV7(0, random)).toBe("00000000-0000-7abc-9234-56789abcdef0");
  });

  it("sorts later ids after earlier ones", () => {
    const random = new Uint8Array(10);

    expect(uuidV7(1_000, random) < uuidV7(1_001, random)).toBe(true);
  });

  it("refuses too few random bytes", () => {
    expect(() => uuidV7(0, new Uint8Array(9))).toThrow(/10 random bytes/);
  });
});
