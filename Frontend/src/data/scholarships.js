export function dedupeByScholarshipId(records) {
  const seen = new Set();
  return records.filter((record) => {
    const id = record?.scholarship_id ?? record?.id;
    if (id == null) return true;
    const key = String(id);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
