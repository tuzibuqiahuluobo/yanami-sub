/** Human descriptions; persisted preset IDs remain the core's IDs. */
export function presetLabel(id: string, fallback: string, en: boolean): string {
  const labels: Record<string, [string, string]> = {
    default: ["标准处理：API 优先", "Standard processing · API first"],
    "agy-hybrid": ["混合处理：API 与 Antigravity", "Hybrid · API and Antigravity"],
    agy: ["Antigravity：使用本地 CLI", "Antigravity · local CLI"],
    "agy-fast": ["Antigravity：快速纯文本纠错", "Antigravity · fast text correction"],
    fast: ["API：快速纯文本纠错，不联网检索", "API · fast text correction, no retrieval"],
  };
  return (labels[id]?.[en ? 1 : 0] ?? fallback) + " · " + id;
}

export function policyLabel(id: string, en: boolean): string {
  const labels: Record<string, [string, string]> = {
    "agent-text-preferred": ["允许 API 与 Agent（按模型组顺序）", "Allow API and Agents (group order)"],
    "api-only": ["只使用 API", "API only"],
    "agent-only": ["只使用 Agent", "Agents only"],
  };
  return (labels[id]?.[en ? 1 : 0] ?? id);
}
