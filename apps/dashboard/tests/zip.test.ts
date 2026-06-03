import { describe, expect, it } from "vitest";
import { createZip, crc32 } from "../src/lib/zip.ts";

const enc = new TextEncoder();

describe("crc32", () => {
  it("matches known vectors", () => {
    expect(crc32(enc.encode(""))).toBe(0);
    // CRC-32 of "123456789" is the standard check value 0xCBF43926.
    expect(crc32(enc.encode("123456789")) >>> 0).toBe(0xcbf43926);
  });
});

describe("createZip", () => {
  it("produces a valid archive with the expected structure", () => {
    const zip = createZip([
      { name: "a.txt", data: enc.encode("hello") },
      { name: "dir/b.txt", data: enc.encode("world") },
    ]);
    const dv = new DataView(zip.buffer, zip.byteOffset, zip.byteLength);
    // starts with a local file header signature
    expect(dv.getUint32(0, true)).toBe(0x04034b50);
    // ends with the End Of Central Directory record
    const eocd = zip.length - 22;
    expect(dv.getUint32(eocd, true)).toBe(0x06054b50);
    expect(dv.getUint16(eocd + 10, true)).toBe(2); // total entries

    // file names appear verbatim in the bytes
    const text = new TextDecoder().decode(zip);
    expect(text).toContain("a.txt");
    expect(text).toContain("dir/b.txt");
    expect(text).toContain("hello");
    expect(text).toContain("world");
  });

  it("handles an empty archive", () => {
    const zip = createZip([]);
    expect(zip.length).toBe(22); // just the EOCD
    const dv = new DataView(zip.buffer, zip.byteOffset, zip.byteLength);
    expect(dv.getUint32(0, true)).toBe(0x06054b50);
    expect(dv.getUint16(10, true)).toBe(0);
  });
});
