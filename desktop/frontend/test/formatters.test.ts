import assert from "node:assert/strict";
import test from "node:test";

import {
  formatBytes,
  formatCapability,
  formatDuration,
  formatPercent,
  formatTaskLog,
  formatUpdateSummary,
  invalidOutputName,
  isUrlSource,
  summarizeTaskError,
} from "../lib/formatters";


test("task log lines preserve original event time and multilingual content", () => {
  const event = {
    timestamp: "2026-09-30T01:02:03.456Z",
    payload: { message: "正在识别 Recognition / café / 日本語 ✅\r\n  错误 Error" },
  };
  const lines = formatTaskLog(event).split("\n");
  assert.equal(lines.length, 2);
  assert.match(lines[0]!, /^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.456[+-]\d{2}:\d{2}\] 正在识别 Recognition \/ café \/ 日本語 ✅$/);
  const prefix = lines[0]!.slice(1, lines[0]!.indexOf("]")).replace(" ", "T");
  assert.equal(new Date(prefix).getTime(), new Date(event.timestamp).getTime());
  assert.equal(lines[0]!.slice(0, lines[0]!.indexOf("]") + 1), lines[1]!.slice(0, lines[1]!.indexOf("]") + 1));
  assert.ok(lines[1]!.endsWith("  错误 Error"));
  assert.equal(formatTaskLog({ ...event, timestamp: "2026-09-30T01:02:03.456+00:00" }), formatTaskLog(event));
  assert.equal(event.payload.message, "正在识别 Recognition / café / 日本語 ✅\r\n  错误 Error");
});

test("invalid timestamps do not throw or retime historical logs", () => {
  assert.equal(formatTaskLog({ timestamp: "bad", payload: { message: "你好 Hello\nError" } }),
    "[unknown time] 你好 Hello\n[unknown time] Error");
  assert.equal(formatTaskLog({ timestamp: "bad", payload: { message: "" } }), "");
});


test("missing translation key is neutral capability copy", () => {
  assert.deepEqual(formatCapability({ translation: false }), {
    tone: "neutral",
    title: "翻译功能未配置",
    detail: "不影响生成原始字幕",
  });
});


test("bytes and progress never display NaN", () => {
  assert.equal(formatBytes(undefined), "—");
  assert.equal(formatBytes(Number.NaN), "—");
  assert.equal(formatPercent(0, 0), "0%");
  assert.equal(formatPercent(undefined, undefined), "0%");
});


test("duration remains compact for long tasks", () => {
  assert.equal(formatDuration(65), "1:05");
  assert.equal(formatDuration(3_725), "1:02:05");
});


test("update summary distinguishes app and full packages", () => {
  assert.equal(
    formatUpdateSummary({
      available: true,
      version: "1.2.0",
      kind: "app",
      releaseNotes: "",
      mandatory: false,
      size: 18 * 1024 * 1024,
    }),
    "发现 1.2.0 · 轻量补丁 · 18.0 MB",
  );
  assert.equal(
    formatUpdateSummary({ available: false, version: "1.1.0" }),
    "已经是最新版本",
  );
});


test("URL sources are recognised the same way the backend recognises them", () => {
  // finesub_bootstrap.capabilities.is_url decides whether yt-dlp gets fetched;
  // if the UI disagreed it would accept an input the backend then refuses.
  assert.equal(isUrlSource("https://example.test/v"), true);
  assert.equal(isUrlSource("http://example.test/v"), true);
  assert.equal(isUrlSource("C:/media/a.mp4"), false);
  assert.equal(isUrlSource("/home/me/a.mp4"), false);
  assert.equal(isUrlSource("ftp://example.test/v"), false);
  assert.equal(isUrlSource(""), false);
});

test("output names are rejected exactly where the backend rejects them", () => {
  // Mirrors TaskRequest.validate_name. The start button is disabled on this, so
  // a mismatch would either block a legal name or let the backend answer with
  // its generic "invalid task parameters".
  assert.equal(invalidOutputName(""), false);
  assert.equal(invalidOutputName("   "), false);
  assert.equal(invalidOutputName("my-clip"), false);
  assert.equal(invalidOutputName("片段 01"), false);
  assert.equal(invalidOutputName("nested/name"), true);
  assert.equal(invalidOutputName("nested\\name"), true);
  assert.equal(invalidOutputName("."), true);
  assert.equal(invalidOutputName(".."), true);
  assert.equal(invalidOutputName("  ..  "), true);
});

test("task errors are concise while preserving the raw detail for a tooltip", () => {
  assert.equal(
    summarizeTaskError(
      "CapabilityUnavailableError: retrieval=native has no usable endpoint\n" +
        "  - research R2 needs native_search",
    ),
    "当前模型不支持所选联网能力，请改用本地检索或更换模型。",
  );
  assert.equal(
    summarizeTaskError("Traceback (most recent call last):\nModuleNotFoundError: x"),
    "运行环境缺少依赖，请打开资源页面安装并重试。",
  );
  assert.equal(
    summarizeTaskError(
      "Traceback (most recent call last):\n" +
        "  File \"worker.py\", line 4, in run\n" +
        "RuntimeError: output worker stopped",
    ),
    "RuntimeError: output worker stopped",
  );
});
