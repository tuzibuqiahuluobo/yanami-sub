# Download route fix

Goal: Let users see and change the Python dependency download route, with the choice taking effect on the next install attempt.

- [complete] Phase 1 — backend route preference and bridge API
- [complete] Phase 2 — resource-page route control and localization
- [complete] Phase 3 — focused tests, build, and visual verification
- [complete] Phase 4 — inspect upstream, repository, and RC6 release conventions
- [complete] Phase 5 — set RC6.2 version and update release metadata
- [complete] Phase 6 — run release-grade tests and build the installer
- [complete] Phase 7 — commit, push, publish RC6.2, and verify assets/manifests

## Resource installation and settings layout follow-up

Goal: Make AI dependency failures recoverable with a verified manual download path, fix the installation failure where possible, and align the settings/resource actions with existing UI controls.

- [complete] Phase 8 — trace the failed wheel, installer, and affected UI flows
- [complete] Phase 9 — implement installation recovery and manual download guidance
- [complete] Phase 10 — refine update/resource layouts and bilingual copy
- [complete] Phase 11 — run focused checks and inspect the resulting UI

Scope boundary: do not add segmented PyTorch downloading in this change.

## RC6.3 release

Goal: Publish the completed dependency-recovery and UI fixes as Yanami Sub `0.1.0-rc.6.post3` (RC6.3), with the installer and signed online update manifest.

- [complete] Phase 12 — confirm upstream, remote state, release requirements, and exact source diff
- [complete] Phase 13 — update RC6.3 version, release notes, and bundled history
- [complete] Phase 14 — run release-grade tests and build all packages and installer
- [complete] Phase 15 — verify hashes, signature, version metadata, and full-update compatibility
- [complete] Phase 16 — commit, push, publish prerelease, and verify remote assets

Scope boundary: do not merge new FineSub changes without separate approval; do not add Authenticode or segmented PyTorch downloading.

## Download reliability and speed follow-up

Goal: Improve RC6.3's Python dependency download experience for mainland and international networks without changing the pinned FineSub dependency versions or hashes. Do not publish a release unless requested.

- [complete] Phase 17 — recheck FineSub upstream and recover prior implementation context
- [complete] Phase 18 — trace actual uv/source/proxy/progress flow and select the smallest safe improvements
- [complete] Phase 19 — implement source/proxy recovery and dependency download resilience
- [complete] Phase 20 — expose actionable live progress and diagnostics in the existing resource UI
- [complete] Phase 21 — run focused and full regression checks, then report what remains unverified on real mainland networks

Scope boundary: no automatic upstream merge, no unverified mirror or third-party proxy, no paid hosting, no disabled TLS/hash checks, no release, and no claim that any route is universally fastest.

## RC6.4 release

Goal: Publish the tested download reliability changes as Yanami Sub `0.1.0-rc.6.post4` (RC6.4), including the Chinese installer and signed online update manifest.

- [complete] Phase 22 — confirm FineSub upstream, GitHub release state, and exact local scope
- [complete] Phase 23 — update version metadata, release notes, and bundled history
- [complete] Phase 24 — run release-grade checks and build installer/update packages
- [complete] Phase 25 — verify hashes, signature, packaged code, and full-update compatibility
- [complete] Phase 26 — commit, push, publish prerelease, and verify remote assets

Scope boundary: no unapproved upstream merge, Authenticode signing, or custom segmented downloader.

## RC6.4 torch download stall report

Goal: Explain from the reported log and current code why the 2.6 GiB torch download appears stuck, what pause/resume actually does, and the smallest evidence-based next step. Diagnostic only; no product code changes or new release.

- [complete] Phase 27 — capture report, confirm upstream and repository state
- [complete] Phase 28 — trace subprocess, timeout, pause/resume, source selection, and UI progress behavior
- [complete] Phase 29 — identify what can and cannot be concluded, propose safe user workaround and next implementation option

## RC6.4 installation failure and log UI follow-up

Goal: Remove the redundant three-line log preview, make a verified manually downloaded CTranslate2 wheel installable, and stop treating local uv-cache failures as proxy failures. Do not publish a release unless requested.

- [complete] Phase 30 — inspect current install/lock/cache flow and reproduce both reported failures
- [complete] Phase 31 — make the smallest backend and log UI corrections
- [complete] Phase 32 — run focused and regression tests, verify the resulting diff, and explain recovery for already affected users

Scope boundary: no FineSub upstream merge without approval, no change to pinned dependency versions or hashes, no release or push.

## RC6.5 release

Goal: Publish the tested local-wheel, uv-cache recovery, and log UI fixes as Yanami Sub `0.1.0-rc.6.post5` (RC6.5), including the Chinese installer and signed online update manifest.

- [complete] Phase 33 — confirm FineSub upstream, GitHub state, signing key, release scripts, and exact source scope
- [complete] Phase 34 — update RC6.5 version surfaces, release notes, docs, and bundled history
- [complete] Phase 35 — run release-grade checks and build installer plus full/app update archives
- [complete] Phase 36 — verify packaged code, hashes, signed manifest, version metadata, and full-update compatibility
- [complete] Phase 37 — commit, push, publish prerelease with all assets, and verify remote state; GitHub's releases-list asset field remains empty despite eight uploaded assets, so in-app discovery is not yet working

Scope boundary: do not merge FineSub upstream without approval; no Authenticode certificate or unrelated features. The frozen launcher changed, so older clients must receive the complete update package.

## RC6.5 application-update discovery repair

Goal: Make signed desktop updates discoverable when GitHub's Releases list omits embedded assets, and determine an honest upgrade path for already installed RC6.4 clients.

- [complete] Phase 38 — check FineSub upstream, live GitHub responses, clean source state, and the full update-selection flow
- [complete] Phase 39 — implement the smallest safe asset-list fallback with regression tests
- [complete] Phase 40 — run focused/full checks and verify against live GitHub metadata
- [complete] Phase 41 — publish RC6.6 with the fallback and verify the signed assets; GitHub's collection still reports zero embedded assets for RC6.6, so the old launcher does not discover it, while the new launcher does
- [blocked] Phase 42 — restore in-app discovery for already installed RC6.5 and earlier clients without replacing historical releases or weakening signed-manifest checks; GitHub must repair the collection response, or users must perform one manual RC6.6 installation

Scope boundary: do not weaken signature/hash validation, mutate historical releases, or replace already published binaries without explicit justification and verification.

## RC6.6 startup crash in local Agent discovery

Goal: Make startup tolerate an inaccessible Windows npm/Agent path (WinError 448) without disabling healthy local Agent detection or altering the user's installed tools.

- [complete] Phase 43 — confirm upstream state, traceback path, all discovery callers, and existing test coverage
- [complete] Phase 44 — add the smallest shared filesystem-error guard and regression tests
- [complete] Phase 45 — focused tests pass 4/4, full desktop Python regression passes 473/473, and the fix is confirmed to require a new full installer because local-Agent detection is frozen into the launcher

Scope boundary: do not touch the user's `.cargo`/Claude Code installation; do not publish a version unless requested.

## RC6.7 startup recovery release

Goal: Publish Yanami Sub `0.1.0-rc.6.post7` with the tested WinError 448 startup fix, Chinese Setup, complete update package, checksums, and signed online update manifest.

- [complete] Phase 46 — confirm FineSub upstream, exact local fix, remote main/tag state, and existing signing key
- [complete] Phase 47 — update version surfaces, release notes, bundled history, and installation guidance
- [complete] Phase 48 — rerun release-grade tests and build the frozen application, archives, and installer
- [complete] Phase 49 — verify packaged startup code, manifest signature, hashes, versions, and full-update selection
- [complete] Phase 50 — commit, push, publish prerelease, and verify all remote assets and update discovery

Scope boundary: no upstream merge, Authenticode certificate, user tool changes, or unrelated features. Since startup cannot reach the UI on affected RC6.6 installations, release notes must direct those users to the full installer.

## RC6.8 dark theme and SOCKS model-download repair

Goal: Make dark mode a coherent low-glare charcoal UI and allow model-weight downloads through an explicitly configured SOCKS proxy; then publish Yanami Sub RC6.8 with the normal installer and signed online update manifest.

- [complete] Phase 51 — confirm upstream, inspect all theme surfaces and model-download/runtime dependency paths, and choose the smallest safe fixes
- [complete] Phase 52 — implement theme and SOCKS proxy repair with focused regression checks
- [complete] Phase 53 — validate light/dark rendering, model-download behavior, and full test suites
- [complete] Phase 54 — version RC6.8, build installer and update assets, verify hashes/signature/full-update selection
- [complete] Phase 55 — commit, push, publish prerelease, and verify public attachments and update discovery

Scope boundary: no upstream merge unless separately approved; no Authenticode certificate; do not change a user's proxy, installed Python, or model cache. Preserve direct/proxy support and pinned model revisions.

## RC6.8 model-download proxy refusal follow-up

Goal: Make model prefetch and normal tasks avoid a dead SOCKS proxy, recover safely from transport failures without mislabeling a healthy mirror as broken, and check adjacent download-path regressions. Do not publish a release unless requested.

- [complete] Phase 56 — inspect the user traceback, trace model prefetch/worker environment and upstream fallback, and recheck FineSub upstream
- [complete] Phase 57 — implement bounded proxy-route handling and clear diagnostics with focused regression tests
- [complete] Phase 58 — audit related model-download/task-worker paths and run focused plus full regression checks

Scope boundary: no upstream merge, no Authenticode, no model-cache deletion, no unverified download source, and no release/push.

## RC6.9 release

Goal: Publish the tested model-download proxy refusal repair as Yanami Sub `0.1.0-rc.6.post9` (RC6.9), with a complete installer and signed online update manifest.

- [complete] Phase 59 — confirm FineSub upstream, remote release/tag state, signing key, and exact source scope
- [complete] Phase 60 — update RC6.9 version, notes, bundled history, and installation guidance
- [complete] Phase 61 — rerun release-grade checks and build installer plus update archives
- [complete] Phase 62 — verify hashes, signature, package contents, and full-update selection
- [complete] Phase 63 — commit, push, publish prerelease, and verify remote assets plus in-app discovery

Scope boundary: no upstream merge without approval, no Authenticode certificate, no user model-cache or proxy-setting changes.

## Hugging Face model-download warning follow-up

Goal: Handle the unauthenticated Hub and unsupported-Windows-symlink notices without misrepresenting them as download failures, while preserving safe model caching and clear user guidance. Do not publish unless requested.

- [complete] Phase 64 — recheck FineSub upstream and trace the exact prefetch, worker, environment, and resource-log paths
- [complete] Phase 65 — implement the smallest accurate warning/optional-auth handling and regression checks
- [complete] Phase 66 — run focused and relevant full tests, inspect logs/UI copy, and report remaining platform limitations

Scope boundary: do not require a paid Hugging Face plan, administrator rights, Developer Mode, or an account; do not suppress actual download errors, alter the user's model cache, or publish a release.

## Subtitle-processing log encoding follow-up

Goal: Trace every subtitle-processing stage and repair text decoding/transport so Chinese, English, and mixed logs display correctly. Preserve existing work and do not publish unless requested.

- [complete] Phase 67 — recheck FineSub upstream and map processing stages, subprocess encoding boundaries, log persistence, API transport, and frontend rendering
- [complete] Phase 68 — implement the smallest shared encoding repair with stage-specific regression checks
- [complete] Phase 69 — run focused and full checks for Chinese, English, and mixed logs; review remaining external-tool limitations
- [complete] Phase 70 — trace task navigation state and the existing lower-right download progress ball, then map task lifecycle/animation settings
- [complete] Phase 71 — reuse the existing progress-ball design for background subtitle processing and completion in both themes/languages
- [complete] Phase 72 — verify task switching, completion, animation-off, reduced-motion, and frontend regression/build

Scope boundary: no upstream merge without approval; no version bump, release, or modification of existing user logs. Background status should not duplicate the task-page progress.

## Task log export and correction/translation stall follow-up

Goal: Make task-log export actually create a discoverable file and offer an open-location action after success; determine from real code/log evidence whether long correction/translation waits come from the desktop shell, pinned FineSub core, DeepSeek Harness, or the selected model. Fix an in-scope shell defect if found. Do not publish unless requested.

- [complete] Phase 73 — recheck FineSub upstream, trace export from button through bridge/filesystem, and reproduce the failure
- [complete] Phase 74 — repair export and add a localized post-export open-location action in the existing UI style
- [complete] Phase 75 — trace the correction/translation stage, DSH calls, timeout/retry behavior, and real task logs; separate warning from blocking cause
- [complete] Phase 76 — distinguish core retrieval/DSH/knowledge failures from a shell hang; retain actionable diagnostics
- [complete] Phase 77 — run focused and full regression and inspect the native-style UI; release became separately authorized afterward

## Per-task API / Agent source choice and safe fallback

Goal: Make the model source explicit on New Task and Batch, default to free API when present and Agent otherwise, and use ordered available Agents with failure details. If no Agent can serve correction, preserve original subtitles and visibly mark correction skipped; never claim translated output exists. Do not change the pinned upstream core or publish without request.

- [complete] Phase 78 — inspect existing route selection, core model-group fallback, and the real failing DSH capsule
- [complete] Phase 79 — implement per-task source choice and ordered Agent routing without mutating shared user config
- [complete] Phase 80 — distinguish all-Agent correction failure from downstream knowledge failure and preserve honest output/stage state
- [complete] Phase 81 — add backend/frontend regression coverage, inspect source selection, and surface per-Agent failures in task/batch logs

Scope boundary for the implementation: preserve all earlier uncommitted changes and user task data; no upstream merge, Authenticode work, or key disclosure.

## RC6.10 release

Goal: Publish the verified HF-warning, text-encoding, background-progress, log-export, and model-source/recovery fixes as `0.1.0-rc.6.post10` (RC6.10), with a complete Windows installer and signed beta online update manifest.

- [complete] Phase 82 — recheck FineSub upstream and GitHub release state, confirm release key and exact local scope
- [complete] Phase 83 — update RC6.10 version surfaces, release notes, bundled history, and installation guidance
- [complete] Phase 84 — run release-grade tests, typecheck, static frontend export, frozen build, and installer
- [complete] Phase 85 — verify signed manifest, archive hashes/contents, installer metadata, and old-client full update selection
- [complete] Phase 86 — commit, push, publish prerelease, and verify eight public assets plus live in-app update discovery

Scope boundary: no upstream merge or unrequested Authenticode work; do not delete user data or generated workspaces. Include every fix since RC6.9, not only the latest Agent change.

## RC6.10 same-version patch replacement

Goal: Fix API/automatic task routing so a Gemini Free key does not make FineSub's correction-window preflight reject a search-only model, then rebuild and replace the existing RC6.10 release with the corrected installer, update packages, hashes, and signed online manifest. Do not bump the version or merge upstream without approval.

- [complete] Phase 87 — check upstream, reproduce the bad dynamic route, and select a correction-eligible model roster
- [complete] Phase 88 — fix source selection, add regression coverage, and update RC6.10 notes/history
- [complete] Phase 89 — rerun release-grade checks, rebuild all eight assets, and verify signature, payload, and same-version updater behavior
- [complete] Phase 90 — update commit/tag, replace the RC6.10 prerelease atomically as practical, and verify all public assets/live discovery

Existing RC6.10 installations cannot discover a same-version replacement through version comparison; they require a manual overwrite. RC6.9 and earlier can discover the newly signed RC6.10 package.

## RC6.10 still reports the old API route

Goal: Identify which executable/app version produced the user's unchanged eight-target API log, compare the installed route code and update pointer with the corrected public RC6.10 package, and fix any proven application or delivery defect without deleting user data or silently changing upstream.

- [complete] Phase 91 — recheck upstream and compare the reported route signature with source, published payload, running process, and installed version pointer
- [complete] Phase 92 — distinguish stale installation/cached same-version update from a code or packaging regression; choose the smallest safe correction
- [complete] Phase 93 — verify the correction or give exact manual recovery steps, clearly stating what was and was not tested

## Errors encountered

- Playwright CLI's Windows wrapper could not start because the machine's WSL/bash entry point returned `CreateInstance/E_ACCESSDENIED`; `npx --no-install playwright-cli` confirmed the CLI package is not cached. Reused the repository's already-installed `playwright-core` and Edge for local preview without adding a dependency.
- A focused pytest run again hit the sandbox's temporary-directory access denial before assertions; the exact suite passed outside the sandbox. The first full Python command also named a nonexistent repository-level `tests` directory; rerunning the actual `desktop/backend/tests` and `desktop/scripts/tests` directories passed 494 tests in total.
- A read-only search initially named a nonexistent `src/finesub/llm/retrieval` directory; the actual web-search and research implementations are `src/finesub/llm/web_search.py` and `search_loop.py`.

- A read-only search named nonexistent `desktop/backend/resources/context.py` and `desktop/backend/resources/status.py`; continued with the actual `DesktopResourceService.worker_context` and resource model files.

- A read-only `rg` attempt used a Windows-invalid wildcard path for test files; search by `rg --files`/directory globs instead.
- Focused export tests first hit the sandbox's temp-directory denial; rerunning with normal test permissions passed all 96 tests.
- Capsule file discovery was denied inside the sandbox; a read-only elevated inspection of the exact DSH capsule found `dsh: QUOTA: Insufficient Balance` in `events/stderr.log`.
- One read-only command used a misspelled workdir without the final `的壳`; reran at the validated repository path.
- The first pytest command inherited `addopts=-n` without xdist in the system interpreter; reran with `-o addopts=`. The sandbox then denied pytest's workspace temp directory; reran the focused suite with local filesystem permission and all 107 tests passed.
- The system Python full suite could not collect GUI tests because `pystray` is absent from that interpreter. Used the repository's existing `.venv-desktop` and the full suite passed 482 tests.

- A read-only live update check first reproduced GitHub's RC6.5 inline `assets: []`; the new release-specific endpoint fallback then selected RC6.5 with all eight assets. Updating a manifest asset's display label did not repair the collection response.
- First full updater-discovery regression run passed 470 tests but hit the known transient Windows `os.replace` access denial in unrelated `test_app_install_switches_pointer_only_after_validation`; rerun it with a fresh pytest temp root, then repeat the full suite if it passes.
- Sandboxed pytest could not access its new `--basetemp` directory; the exact focused suite passed outside the filesystem sandbox (`18 passed`).
- Sandboxed Node tests failed uniformly with `spawn EPERM` before running assertions; the exact frontend suite passed outside the process sandbox (`95 passed`).

- A first isolated uv probe command used an invalid workdir spelling and never started; rerunning with the exact repository path succeeded. No product or user install data was changed by that failed command.

- The UI/UX skill's `scripts` path resolves to a missing `search.py` in this environment; use its fully read accessibility/progressive-disclosure guidance and the product's existing design instead of generating a new design system.

- This diagnostic first searched nonexistent `desktop/backend/resources/manager.py`, `desktop/frontend/components/ProgressBar.tsx`, and `desktop/backend/common/paths.py`; continued against the concrete files returned by `rg` without altering product code.

- The first uv 0.12.17 China-lock dry-run rejected the existing dotted `pylock.win-py312.cn.toml` filename; a temporary byte-identical `pylock.win-py312-cn.toml` passed. This was a real new-uv compatibility issue, not a mirror/network failure.
- One full backend run hit an unrelated transient Windows access denial while renaming an updater test's staging directory. The exact test passed in a fresh temporary root; the next full suite passed.

- Initial `rg` searched a non-existent repository-level `src` directory; the pinned upstream source is staged under `tmp/release-upstream-v0.5.1` during this checkout.
- First torch lock regex was malformed in PowerShell quoting; replaced with fixed-string searches.
- Direct `curl` HEAD probes failed in this environment with Schannel credential errors; source selection was confirmed from local route state and install logs instead.
- The first combined frontend patch did not match the exact React import line and was rejected atomically; split the patch into smaller exact edits.
- First pytest run could not create its default temp root under `%TEMP%`; rerun with an explicit workspace `--basetemp`.
- First Next build failed with sandbox `spawn EPERM`; run type/tests in place, then retry the build with the required execution permission if needed.
- Playwright's Windows wrapper could not run because WSL/bash is absent; direct `npx` then hit a pre-existing npm cache `EEXIST`. Do not delete the user's npm cache for visual QA; use the available app browser instead.
- Ruff is not installed in the desktop virtual environment; imports and wrapping were checked manually after `git diff --check` passed.
- The final focused pytest rerun hit the same sandbox temp-directory denial; the identical test passed outside the sandbox (`1 passed`, `35 deselected`).
- An overly broad tracked-text search descended into generated frontend artifacts and produced truncated output; subsequent searches use `git grep` or explicitly scoped paths.
- `C:\Users\Ikun\key.pem` and `root_key.pem` are not Ed25519 update-signing keys; locate the previously used RC6 manifest key before building rather than generating a replacement that installed clients would reject.
- Filename/header searches under Documents, Downloads, Desktop, and the Windows temp directory found no additional Ed25519 PEM; inspect prior release command metadata for the key path without printing secret material.
- First RC6.2 full test run found two expected contract assertions that still described the old surface: the public bridge API list omitted the two new route methods, and the bundled-history test still expected 7 entries instead of 9. Update those assertions, then rerun the same suites.
- Second Python suite run reached 446 passes but one unrelated updater install test hit a transient Windows `os.replace` access denial in the pytest temp tree; rerun that test in a fresh temp root before deciding whether any code change is warranted.
- The first manifest verification command used the verifier's default `stable` channel against this intentional `beta` release; rerun with `expected_channel='beta'`. Installer ProductVersion printed correctly but the initial PowerShell equality check returned false, so inspect the raw string before treating it as a build defect.
- `npm audit --omit=dev` reports current advisories in Next 16.2.11 and transitive build packages. The shipped product is a static export with no Next server, image optimizer, Node runtime, or `node_modules`, so these server/build-time paths are absent from the installer; defer the framework update to an isolated dependency release.
- The first browser preview was opened without `?preview=1` and timed out waiting for the native bridge; reopening in the built-in preview mode resolved it.
- Visual QA caught a generic switch-grid span overriding the new update-section single-column layout; added an explicit column for the auto-check row and confirmed the buttons now sit below release notes.
- The first full Python run had one expected public-bridge API-list assertion missing the new dependency-download method; updated the contract, then reran all tests.
- RC6.3's first release-asset build omitted the explicit `-ReleaseNotes` argument, producing a valid but empty announcement. Rebuild only the generated app/full archives and signed manifest from the already verified bootstrap with the new notes; do not publish the first manifest.
- The first release verifier search used `desktop/backend/updater` but this repository's package is `desktop/backend/updates`; search the actual module path.
- A staged app version directory did not contain `manual_wheels.py` because the resource adapter belongs to the frozen launcher, not the updateable application payload; the PyInstaller archive viewer confirmed `desktop.backend.resources.manual_wheels` is bundled in the EXE.
