/** Plain React text only: knowledge can contain untrusted imported material. */
export function KnowledgeDocument({ text, empty }: { text: string; empty: string }) {
  const lines = text.replace(/<!--[\s\S]*?-->/g, "").trim().split(/\r?\n/);
  return <div className="knowledge-readable">
    {lines.some((line) => line.trim()) ? lines.map((line, index) => {
      if (/^#{1,6}\s+/.test(line)) return <h3 key={index}>{line.replace(/^#{1,6}\s+/, "")}</h3>;
      return line.trim() ? <p key={index}>{line}</p> : null;
    }) : <p>{empty}</p>}
  </div>;
}
