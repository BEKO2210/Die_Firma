import { afterEach, describe, expect, it } from "vitest";
import { DEFAULT_LANG, createT, getLang, interpolate, messages } from "../src/lib/i18n.ts";

const ENV = process.env.DIE_FIRMA_LANG;
afterEach(() => {
  if (ENV === undefined) delete process.env.DIE_FIRMA_LANG;
  else process.env.DIE_FIRMA_LANG = ENV;
});

describe("dashboard i18n", () => {
  it("defaults to German and reads the env override", () => {
    delete process.env.DIE_FIRMA_LANG;
    expect(getLang()).toBe(DEFAULT_LANG);
    process.env.DIE_FIRMA_LANG = "en";
    expect(getLang()).toBe("en");
    process.env.DIE_FIRMA_LANG = "fr"; // unsupported -> default
    expect(getLang()).toBe(DEFAULT_LANG);
  });

  it("translates per language", () => {
    expect(createT("de")("form.submit")).toBe("Auftrag aufgeben");
    expect(createT("en")("form.submit")).toBe("Submit job");
  });

  it("falls back to English then to the key", () => {
    const cat = messages("de");
    // every English key is present in the merged catalogue
    expect(cat["metric.tokensPerSec"]).toBeDefined();
    expect(createT("en")("totally.unknown.key")).toBe("totally.unknown.key");
  });

  it("interpolates placeholders and leaves unknown ones intact", () => {
    expect(interpolate("{p}% ({n} Tokens)", { p: 40, n: "1.2k" })).toBe("40% (1.2k Tokens)");
    expect(interpolate("{a}-{b}", { a: 1 })).toBe("1-{b}");
    expect(interpolate("no vars")).toBe("no vars");
  });

  it("de and en catalogues have identical key sets (no drift)", () => {
    const en = Object.keys(messages("en")).sort();
    const de = Object.keys(messages("de")).sort();
    expect(de).toEqual(en);
  });
});
