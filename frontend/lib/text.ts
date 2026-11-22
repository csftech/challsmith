export type Enc = { bom: boolean; crlf: boolean };

// Decode a file for the editor. Returns null when the bytes cannot round-trip through the editor
// (not UTF-8, or mixed/lone-CR line endings), so saving can never alter bytes the author did not touch.
export function decode(buf: Uint8Array): { text: string; enc: Enc } | null {
  let raw: string;
  try {
    raw = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(buf);
  } catch {
    return null;
  }
  const bom = raw.startsWith("﻿");
  if (bom) raw = raw.slice(1);
  const crlf = raw.includes("\r\n");
  const text = crlf ? raw.replace(/\r\n/g, "\n") : raw;
  if (text.includes("\r")) return null; // CodeMirror would turn a lone CR into a line break
  const enc = { bom, crlf };
  const back = encode(text, enc);
  if (back.length !== buf.length || back.some((b, i) => b !== buf[i])) return null;
  return { text, enc };
}

export function encode(text: string, enc: Enc): Uint8Array {
  const body = enc.crlf ? text.replace(/\n/g, "\r\n") : text;
  return new TextEncoder().encode((enc.bom ? "﻿" : "") + body);
}
