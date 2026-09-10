# FineSub core compatibility

FineSub Desktop `0.1.x` is built and tested against the exact upstream
[FineSub `v0.5.0`](https://github.com/caca2331/finesub/releases/tag/v0.5.0)
source snapshot. The desktop repository owns presentation, Windows integration,
resource installation, and update delivery; FineSub core remains the only owner
of subtitle processing, scheduling, model routing, knowledge semantics, and
storage migration.

## Coverage

| Core capability | Desktop support | Boundary |
| --- | --- | --- |
| Local audio/video and URL inputs | Supported | URL jobs request `yt-dlp` only when needed. |
| Every production pipeline stage | Supported | Vocal, aligned, stable, raw SRT, translated SRT, and final SRT are selectable. |
| ASR and separation tuning | Supported | Model, language, device/GPU tier, separation/rate, VAD assist, Qwen verification, language re-decode, context, decode batch, gap, stabilization, word timestamps, and split scale are forwarded to core. |
| LLM correction/translation tuning | Supported | Media per phase, retrieval, difficulty, continuity, parallel windows, fast mode, output scale, per-task model routes, retry budgets, extra context/style, named styles, and resume are forwarded to core. |
| Knowledge collection/update and refined-SRT feedback | Supported | The task form and Knowledge Center use the core knowledge implementation in an isolated worker. |
| Multiple files/URLs | Supported | The batch page uses the core scheduler, worker limits, queue back-pressure, priorities, retries, failure isolation, durable progress, cancel, and resume. |
| API-key pools and custom providers | Supported | Free/paid Gemini pools, Exa, Tavily, and provider keys from the core catalog use the same encrypted `.env`; plaintext export is available through a native Save dialog. |
| Model routing and local-Agent routes | Supported | Core presets, policies, providers, targets, per-task overrides, and non-spending local CLI readiness checks are exposed. |
| Knowledge maintenance and sharing | Supported | Browse revisions, edit/create/retire entries, verify/repair/refresh, ingest, candidates, rollback/restore, refined feedback, remote registration, mark/push/pull, status, and conflict review are available. |
| Runtime setup and health (`setup`, `doctor`) | Supported | The Resources page performs request-specific setup and returns structured diagnostics. |
| Resource mirrors and reuse | Supported | Core manifests/hash checks remain authoritative; downloads can run concurrently, scan local disks first, and use the TUNA PyPI route in mainland China with official fallback. |
| Key export (`keys --out`) | Supported | Export includes readable built-in and catalog-provided keys; the encrypted source file is never overwritten. |
| Big-data relocation (`relocate`) | Supported | A native folder picker calls core's locked, crash-safe relocation and refreshes future single/batch workers without a restart. |
| Rebuildable-data cleanup (`uninstall --purge-big-data`) | Supported | Removes runtime, models, downloads, and Agent capsules only. Finished tasks, subtitles, API keys, preferences, and other personal data are preserved. |

The desktop deliberately publishes finished subtitle files beside a local input
and keeps intermediate task state under the managed task store. This is a
desktop product policy, not a second pipeline implementation.

## Deliberate CLI-only or partial surfaces

These are not missing subtitle-processing features:

- `agent-join` and `agent-task` remain CLI-only. Core `v0.5.0` exposes them as
  terminal-oriented runtime modules, not a structured service suitable for a
  long-lived GUI. Desktop can configure Agent routes and verify local CLIs.
- `agent-ping` spends quota. Desktop currently performs the safe, non-spending
  readiness probe instead of issuing model calls without a task.
- Live append to a running JSONL manifest and arbitrary manifest import/export
  remain CLI-only. Desktop starts and resumes owned batches, but does not yet
  attach an editor to the scheduler's live intake channel.
- Arbitrary `--output`, `--knowledge-root`, `--task-artifact-dir`, and
  `--task-id` are managed by the desktop task store so a web renderer cannot
  escape app-owned paths. `--extra-info-file` is represented by the equivalent
  text field.
- `--test-profile` is a developer/test switch. `--log-level` is replaced by
  the desktop reporter: concise live output plus durable full logs.
- Installing/removing the application itself belongs to the Windows installer.
  The in-app cleanup action removes only core-rebuildable data.

## Core interfaces currently consumed

Desktop adapters call or project these upstream surfaces instead of copying
their business logic:

- `finesub.pipeline.pipeline` and shared validation/constants for one task;
- `finesub.scheduler.run_batch` plus batch state/control files for queues;
- `finesub_bootstrap.ResourceManager`, `RuntimeEnvironment`, resource manifests,
  download routing, locks, paths, and `Shell` storage maintenance;
- the public model-route catalog, execution settings, API-key pool parser, and
  local-Agent driver probes;
- knowledge entry/node/update/share command entry points, invoked only through
  an allowlisted isolated worker.

## Interfaces to request from core next

1. A structured Agent service for join, task listing, next-task, submit,
   cancel, and ping results. This would let Desktop add full Agent operations
   without parsing terminal output or binding private modules.
2. A structured, versioned knowledge administration service. The current
   worker isolation is safe, but still adapts command-style entry points.
3. A typed live-batch intake/control API so a running desktop queue can accept,
   reprioritize, or withdraw rows without editing JSONL files directly.
4. A small compatibility descriptor (core API level plus supported fields), so
   a future Desktop build can reject an incompatible core update with a precise
   message before launching a task.

## Upgrade rule

Do not float an installed Desktop to an untested FineSub branch. For every core
upgrade: pin an exact tag/commit, regenerate the packaged snapshot, run backend
contract tests against that source tree, run frontend type/tests and the static
build, then exercise one local-file task, one URL task, one batch resume, and
one knowledge update before publishing.
