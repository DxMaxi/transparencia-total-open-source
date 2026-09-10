const quote = (value) => `"${value.replaceAll('"', '""')}"`;

export function tableFingerprintQuery(table, schema = "public") {
  const projection = table.columns.map((column) =>
    table.bytea_columns?.includes(column)
      ? `encode(sha256(${quote(column)}), 'hex') AS ${quote(column)}`
      : quote(column),
  ).join(",");
  // Hash actual binary bytes before JSON encoding; never trust a stored digest
  // instead of content, and never materialize large bytea values as hex JSON.
  return `SELECT count(*)::text AS count,
    md5(coalesce(string_agg(fingerprint, '' ORDER BY fingerprint COLLATE "C"), '')) AS fingerprint
    FROM (SELECT md5(row_to_json(original)::text) AS fingerprint
      FROM (SELECT ${projection} FROM ${quote(schema)}.${quote(table.name)}) original) fingerprints`;
}
