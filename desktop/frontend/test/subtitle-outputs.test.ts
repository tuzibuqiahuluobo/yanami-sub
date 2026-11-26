import assert from "node:assert/strict";
import test from "node:test";

import {
  hasRequestedSubtitleOutput,
  preferredTaskOutput,
  preferredSubtitleOutput,
  subtitleOutputEntries,
  taskOutputEntries,
} from "../lib/subtitleOutputs";

test("only a saved result for the requested subtitle stage merits completion motion", () => {
  const raw = { rawSrt: "D:/media/a-raw.srt" };
  const translated = { ...raw, translatedSrt: "D:/media/a-translated.srt" };
  const final = { ...translated, finalSrt: "D:/media/a.srt" };
  assert.equal(hasRequestedSubtitleOutput("raw-srt", raw), true);
  assert.equal(hasRequestedSubtitleOutput("translated-srt", translated), true);
  assert.equal(hasRequestedSubtitleOutput("final-srt", final), true);
  assert.equal(hasRequestedSubtitleOutput("translated-srt", raw), false);
  assert.equal(hasRequestedSubtitleOutput("final-srt", translated), false);
  assert.equal(hasRequestedSubtitleOutput("stable", final), false);
  assert.equal(hasRequestedSubtitleOutput("final-srt", {}), false);
});


test("completed tasks expose subtitles only and prefer the final result", () => {
  const outputs = {
    vocalAudio: "D:/private/a-vocal.ogg",
    rawSrt: "D:/media/a-raw.srt",
    finalSrt: "D:/media/a.srt",
    metadataJson: "D:/private/a-run.json",
  };

  assert.deepEqual(subtitleOutputEntries(outputs), [
    ["finalSrt", "D:/media/a.srt"],
    ["rawSrt", "D:/media/a-raw.srt"],
  ]);
  assert.equal(preferredSubtitleOutput(outputs), "D:/media/a.srt");
});


test("an explicitly requested expert stage is available without becoming a subtitle", () => {
  const outputs = { alignedJson: "D:/private/a-aligned.json" };

  assert.deepEqual(subtitleOutputEntries(outputs), []);
  assert.deepEqual(taskOutputEntries(outputs), [
    ["alignedJson", "D:/private/a-aligned.json"],
  ]);
  assert.equal(preferredTaskOutput(outputs), "D:/private/a-aligned.json");
});
