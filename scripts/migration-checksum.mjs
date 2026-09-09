import { createHash } from "node:crypto";

const sha256 = (value) => createHash("sha256").update(value).digest("hex");

export function matchesMigrationChecksum(bytes, expected) {
  if (sha256(bytes) === expected) return true;
  // Historical V4 deploys used both Git LF and Windows CRLF, with one or two
  // terminal newlines. Internal whitespace and SQL content must remain exact.
  const body = bytes.toString("utf8").replaceAll("\r\n", "\n").replace(/\n+$/, "");
  return ["", "\n", "\n\n"].some((ending) => {
    const lf = body + ending;
    return sha256(lf) === expected || sha256(lf.replaceAll("\n", "\r\n")) === expected;
  });
}
