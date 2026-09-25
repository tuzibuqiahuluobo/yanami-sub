# Progress

## 2026-09-24 Hugging Face warning follow-up

- Rechecked FineSub upstream v0.5.1 and clean RC6.9 source. Traced the resource log through `run_model_prefetch`, the common desktop worker context, and the existing resource-page model note. The screenshot proves neither 429 nor download failure.
- Confirmed from the installed Hub source and official documentation that unsupported Windows symlinks degrade cache space efficiency but not correctness, while `HF_TOKEN` is optional and can be a free-user credential. Chosen scope is a concise log note, documented cache caveat, and warning-only suppression; no paid plan, admin setting, cache mutation, or release.
- Added a shared desktop child environment default that suppresses only the verbose symlink warning, preserving explicit user override and symlink use. The model prefetch log replaces the anonymous notice with one concise nonfatal line; real HTTP 429 errors remain unchanged. Reused the existing bilingual model-help text to explain optional free tokens and Windows disk-space tradeoffs.
- Focused backend resource/prefetch tests passed 60/60, frontend tests 96/96, TypeScript typecheck passed, and `git diff --check` has no whitespace errors. Running full backend regression and production static export next.


## 2026-09-23 RC6.8 model-download follow-up

- User reported a new Whisper failure after RC6.8 and then explicitly authorized fixing the issue plus checking related paths. The supplied traceback shows SOCKS transport `connect_tcp` refused with WinError 10061; RC6.8's bundled SOCKSIO solved the previous import error but not a dead proxy route.
- Read the existing model prefetch, resource service, shared route helper, and normal task worker launch. Reproduced that the exact cross-process `httpx.ConnectError: [WinError 10061]` message is not classified for mirror fallback, and observed that endpoint fallback does not change proxy transport. Rechecked FineSub upstream v0.5.1/main unchanged. Product files remain untouched so far.
- Added an explicit child-process route application that scrubs inherited proxy variables. Model prefetch iterates live proxy routes then direct before changing the Hugging Face endpoint; task workers choose the first checked route at spawn. Transport failures crossing the subprocess pipe now get a network hint and are recognized for the later source fallback. Focused model/resource/job suite passed 107/107 after running outside the sandbox temp-directory denial.
- The adjacent audit found the cached-overseas-region case. Added an automatic official-to-existing-mirror fallback only for network failure and preserved explicit official/custom-source choices. Focused suite passed 109/109; the full desktop Python/scripts suite passed 482/482 in the project's `.venv-desktop` environment. The system Python full run had only collection errors because it lacks `pystray`, not because of code changes.
- Added a live-listener regression for a stopped local SOCKS port, checked that repeated offline failures do not poison the backup mirror health, and extended the transport classifier to the other HTTPX connection I/O errors while excluding disk and authentication errors. Final focused suite passed 111 tests before the last classifier test; final complete Python/scripts suite passed 485/485. `git diff --check` passes. No user runtime/cache was changed, and no commit, push, installer, or release was made.

## 2026-09-23 RC6.8 request

- User requested Codex-like dark-mode polish and a fix for Whisper weight download failing because HTTPX lacks SOCKS support, then added RC6.8 publication after both are verified. Read the frontend-design, UI/UX, ponytail, and planning skills. The UI/UX skill's search script is a missing pointer in this installation; apply its dark-mode/accessibility guidance directly with the project's existing theme system.
- Checked FineSub upstream before edits: latest tag and `main` both remain `v0.5.1` at `b9b2f10`; local tracked tree starts clean at RC6.7 `ea30b99`. No upstream merge is planned.
- Confirmed the managed runtime lock includes HTTPX but omits its SOCKS extra. Bundled the 12,763-byte MIT SOCKSIO wheel from PyPI, SHA-256 `95dc1f15f9b34e8d7b16f06d74b8ccf48f609af32ab33c608d08761c5dcbb1f3`, and put the wheel on both model and task worker PYTHONPATH; no user runtime rebuild or network dependency is needed.
- Refined dark tokens to neutral charcoal layers and added dark-only resource/log/status/form overrides. Local preview screenshots showed the model log at `rgb(29,31,34)` with readable text; light mode retains its original `rgba(255,255,255,.75)` panels. Kept the background-opacity setting meaningful in dark mode as well. Focused backend tests passed 47/47; complete Python regression passed 474/474 after synchronizing the native startup frame color, and the frontend passed 96/96 before the final opacity adjustment.
- RC6.8 files are versioned, and the updated frontend suite passes 96/96 including the dark-opacity regression. TypeScript typecheck passes. The upstream build checkout is clean, the new wheel is staged so the tracked-file packager sees it, and no Authenticode certificate is configured.
- Built production static frontend and frozen RC6.8 app, then Inno Setup. The shipped app wheel's SHA-256 matches official PyPI. Verified the Ed25519-signed beta manifest with the trusted key, both ZIP SHA-256/size and ZIP CRC, wheel content in app/full ZIPs, Setup SHA-256 sidecar, and full-update selection from RC6.7. Setup is intentionally not Authenticode-signed.
- `npm ci` reported four advisories in the frontend build dependency tree. Reviewed the critical Next.js advisory: it concerns Windows-hosted Next servers, while this package ships only static `frontend/out` and no Next server. No dependency upgrade is folded into this RC6.8 bugfix; track build-chain updates separately.
- Committed RC6.8 as `a625e23`, atomically pushed `main` and tag `v0.1.0-rc.6.post8`, and published the public prerelease with eight attachments. The per-release API reported every asset uploaded with matching size and SHA-256. After publication, the public tag API returned `draft=false`, `prerelease=true`, eight assets; the application's own beta-release fetcher found RC6.8 and downloaded/verified its signed manifest successfully.

## 2026-09-23 RC6.7 release

- User explicitly requested RC6.7 publication. Re-read release and planning skills, restored the plan, and checked fresh FineSub tags (v0.5.1 remains latest). Only the two intended local-Agent startup-fix files are tracked modifications; origin/main matches local `6cab193`, RC6.7 tag is absent, and the pinned Ed25519 release key still matches installed clients.
- Versioned the tested startup fix as `0.1.0-rc.6.post7`, updated release notes and Chinese guidance, and added RC6.6 to bundled history. Full Python regression passed 473/473; frontend passed 95/95, TypeScript typecheck, and static export validation.
- Built the frozen Windows application, Chinese Setup, app/full ZIPs, SHA-256 sidecars and Ed25519-signed beta manifest. Verified the exact fix's bytecode inside the frozen launcher matches compiled source, packaged source and full ZIP match, the signed manifest validates, archive hashes/CRC pass, and RC6.6 selects a full update.
- Committed as `ea30b99`, atomically pushed `main` and tag `v0.1.0-rc.6.post7`, then published the RC6.7 prerelease. All eight GitHub attachments report uploaded state, byte sizes and SHA-256 matching local artifacts. The live updater discovers RC6.7 and verifies its signed full update from RC6.6. Users whose RC6.6 crashes before showing the UI still need the Setup to recover.

## 2026-09-23 RC6.6 startup failure

- Read the screenshot and identified uncaught `WinError 448` during automatic local-Agent discovery as the immediate cause of the pre-window crash. Re-read the selected skills and existing plan, ran session catchup, confirmed clean tracked state, and checked that FineSub upstream's newest tag remains v0.5.1.
- Added a per-candidate `OSError` skip in the shared npm entry scanner and a fail-safe around optional discovery at startup; neither changes the user's installed tools. Regression tests cover an inaccessible Claude candidate followed by a healthy one, and a total scan failure that must not abort startup. Focused local-Agent tests pass 4/4.
- Complete Python regression passes 473/473, and `git diff --check` reports no whitespace errors. The fix is limited to two tracked files, remains uncommitted/unpublished, and needs a new full installer because RC6.6 froze the old scanner into its EXE. No system PATH, Cargo, Claude Code, or installed Yanami Sub files were modified.

## 2026-09-23 RC6.6 application-update hotfix

- Followed the user's request to repair in-app update discovery. The GitHub releases collection still returned zero embedded assets for RC6.5 while its individual assets endpoint returned all eight files; RC6.4 and older list entries returned eight.
- Added and tested a release-specific assets-list fallback that retains the existing signed manifest, tag, channel, and SHA-256 checks. The new code selected RC6.5 live, and a regression test covers the inconsistent API response.
- Bumped RC6.6 version surfaces, history, release notes and installation docs. Python regression passed 471/471, frontend 95/95, TypeScript typecheck and static build passed. Initial sandbox runs were blocked by Windows temp-directory and Node subprocess permissions; approved reruns passed.
- Built frozen launcher, Simplified Chinese Setup, app/full archives, checksums, and signed beta manifest. Verified the release key, signature, both ZIP hashes/CRCs, frontend entrypoint, and full-update choice from RC6.4/RC6.5.
- Committed as `767924b`, pushed main and annotated `v0.1.0-rc.6.post6`, then published a prerelease with eight individually verified uploaded assets. The live new selector and downloaded signed manifest identify RC6.6 and select a full update.
- Critical limitation: GitHub's collection response also reports zero embedded assets for RC6.6, while the per-release response reports eight. The old selector therefore still chooses RC6.4. Updated the Release notes and docs to tell older users to install RC6.6 manually once; do not claim the old in-app path is fixed until the collection response recovers. No historical Release was repurposed.

## 2026-09-23 RC6.5 update-discovery repair

- User asked to fix rather than leave manual installation as the answer. Re-read the active plan and skills, checked FineSub tags (still v0.5.1), confirmed clean tracked state, and reproduced the releases-list/individual-assets mismatch.
- Traced the shared update check: its inline-asset gate skips RC6.5, then returns RC6.4 as the newest signed desktop release. Preparing a minimal asset-list fallback and an upgrade-path assessment for installed older clients.
- Added a release-specific asset-list fallback only when the list entry omits assets; it uses a numeric ID and preserves all later signed-manifest checks. The focused updater test file passed 15/15, and a live GitHub check using the patched function returned RC6.5 with eight assets.
- Full Python regression initially passed 470/471 with only a known transient Windows staging rename denial in an unrelated installer test. That exact test passed alone; a fresh complete run passed 471/471.
- Confirmed both published RC6.4 and RC6.5 frozen launchers contain the old selector. GitHub's collection response remains empty for RC6.5 even after a manifest-asset display-label update; the individually listed asset remains uploaded with the same name and SHA-256. The safe client fix is local and tested but cannot be delivered in-app to already installed clients until GitHub's collection index recovers or an explicitly approved alternate migration is chosen. No new release or push was performed in this repair turn.

## 2026-09-23 RC6.5 release

- Restored the completed implementation plan and started RC6.5 release phases. Fresh FineSub tags still end at v0.5.1; no upstream merge is planned.
- Confirmed local branch `codex/rc6-ui-feedback` is at the published RC6.4 commit, origin/main matches it, RC6.5 tag does not yet exist, and only the three intended implementation/test files are tracked modifications.
- Confirmed RC6.4 is a public prerelease with the established eight assets (Chinese installer, app/full ZIPs, three SHA-256 sidecars, signed manifest JSON and signature).

## 2026-09-23 CTranslate2 and log UI follow-up

- Rechecked FineSub upstream tags before edits: latest remains v0.5.1. Restored the previous plan and confirmed no tracked changes.
- Traced the desktop temporary lock rewrite, failure classification, proxy/source retry, uv cache, and duplicate UI preview.
- Reproduced a successful uv 0.12.17 offline CTranslate2 installation from a standards-compliant local `archive.path` in an isolated workspace venv; the SHA-256-verified wheel itself is sound. Preparing the minimal code and regression-test changes.
- Replaced temporary-lock `file:///` URL substitution with a PEP 751 `path` after SHA-256 verification, added one package-scoped uv cache-clean retry for a missing `archive-v0` entry, and kept local failures out of proxy/source fallback.
- Removed the redundant three-line log preview. The one remaining disclosure has the same readable scrollable styling and still receives the existing log tail.
- Focused backend suite passed all 18 cases, frontend suite passed all 95 cases, and TypeScript typecheck passed. The first sandboxed test attempts were blocked by filesystem/process permissions, not assertions; reruns passed with the required execution permissions.
- Full desktop Python suite passed all 470 tests. The frontend production static build succeeded; final focused backend rerun passed 18/18 and `git diff --check` found no whitespace errors.
- Removed only the isolated `tmp/uv-local-wheel-probe` test venv and lock after validating its exact path inside the workspace. Did not alter `E:\Yanami Sub` installation or uv cache, and did not commit, push, build an installer, or publish a release.

- Checked upstream before editing: no release newer than FineSub `v0.5.1`.
- Traced route selection, regional lock fallback, persisted preferences, bridge calls, and resource-page composition.
- Selected minimal scope: persisted `auto/cn/global` route preference, immediate re-probe for auto, visible route selector, and focused tests.
- Added backend route preference, immediate route preparation before Python setup, and bridge method exposure.
- Added the bilingual resource-page selector and reused the existing rounded `CustomSelect`.
- Backend route/resource tests pass: 48 tests.
- Frontend tests pass: 95 tests; TypeScript typecheck and production build also pass.
- Visually verified automatic, mainland-mirror, and official-source switching in the browser preview, including the effective-route badge and success toast.
- Rechecked after cleanup: focused backend route test, TypeScript typecheck, and `git diff --check` all pass.
- RC6.2 release session started; restoring the existing plan before inspecting version and release conventions.
- Confirmed FineSub has no release newer than `v0.5.1`, and GitHub's latest Yanami Sub release is RC6.1 (`v0.1.0-rc.6.post1`).
- Recovered the RC6.1 build/publish convention and confirmed RC6.2 needs a full update because its bridge surface changed.
- Verified the FineSub v0.5.1 build checkout and local toolchain; the update-signing key still needs to be resolved from the prior release workspace.
- Confirmed the expected update key is not among the obvious profile PEM files or transient project folders; continuing with path-only history lookup.
- Recovered and verified the existing Ed25519 release key without exposing private key material; signed online manifests can be produced safely.
- Updated all authoritative version surfaces to `0.1.0-rc.6.post2`, added RC6.2 release notes, refreshed installation docs, and filled the missing RC6/RC6.1 bundled history.
- First release-grade run: TypeScript passes; Python reached 446 passes with one stale public-API expectation; frontend reached 94 passes with one stale history-count expectation.
- After updating contracts, all 95 frontend tests pass. Python reached 446/447 with only a Windows temp-directory rename denial in an unrelated updater test.
- The isolated updater test passes in a fresh temp root, confirming the prior failure was a transient Windows file lock rather than a regression.
- Built the RC6.2 PyInstaller bootstrap, application/full ZIPs, and signed online manifest; the build reran all 95 frontend tests, typecheck, static export, and production build successfully.
- Built the Chinese Inno Setup installer `Yanami-Sub-0.1.0-rc.6.post2-Setup.exe` successfully without Authenticode.
- Added the installer SHA-256 sidecar and confirmed hashes for installer, app ZIP, and full ZIP; continuing manifest/channel and file-version validation.
- Verified the beta manifest signature, release URLs, sizes, empty incremental-compatibility list, installer version metadata, and all local artifact hashes.
- Confirmed remote main/tag availability and reviewed npm audit findings; no shipped runtime exposure was found because the installer contains only the static frontend export.
- Staged only the 24 intended source, test, version, and documentation files; committed RC6.2 as `56731a5` (`release: publish Yanami Sub 0.1.0 RC6.2`).
- Pushed commit `56731a5` to `origin/main` and annotated tag `v0.1.0-rc.6.post2` to GitHub.
- Published Yanami Sub 0.1.0 RC6.2 as a public prerelease with all eight expected assets; GitHub's recorded digests and sizes match the locally verified installer and update packages.
- Confirmed the release is not a draft, remains marked prerelease, targets `main`, and exposes the signed online update manifest at the final tagged download URL.
- Started resource installation and UI follow-up; checked FineSub upstream before changing code and confirmed `v0.5.1` remains latest.
- Traced the exact failing CTranslate2 wheel to a published FineSub asset whose digest matches the lock; verified that uv accepts a local `file://` archive in a dry run.
- Added a desktop-only runtime adapter for longer uv network timeouts and verified local wheel substitution, plus failure metadata and a guided UI panel; implementation checks remain.
- Completed the manual fallback: failures identify the exact locked wheel, open its upstream download, show the cache folder, and reuse a local file only after SHA-256 verification. The canonical FineSub lock and its runtime digest remain unchanged.
- Moved the update controls/status beneath the release notes and matched cache/install folder buttons to the existing rounded resource action. Browser preview exposed and helped fix a generic grid-span conflict.
- Verified a simulated failure panel in the browser, then removed the temporary simulation code. The user's screenshot hides the lower uv error details, so unrelated disk or unpack failures still require the expanded log for a precise diagnosis.
- Final validation passes: 452 Python tests, 95 frontend tests, TypeScript typecheck, and static production build. No installer, commit, push, or release was requested for this follow-up.
- RC6.3 release requested. Re-read the current plan and confirmed FineSub's fresh tag list still ends at v0.5.1; no upstream merge is needed for this release.
- Confirmed the existing public RC6.2 prerelease has all eight expected assets; preparing RC6.3 from the locally tested follow-up diff only.
- Confirmed remote `main` matches RC6.2, no RC6.3 tag exists, the release key and upstream source are present, and the existing build scripts cover the installer, full/app archives, hashes and signed manifest.
- Updated all authoritative RC6.3 version surfaces, root/desktop/usage instructions, signed-manifest release notes, and bundled update history; the new release forces a full update because the bridge API changed.
- RC6.3 release-grade tests passed: 452 Python and 95 frontend tests, TypeScript check, and static Next.js build. The trusted Ed25519 release key matches the pinned public key.
- Built the version-specific PyInstaller application/full update archives and signed manifest; Inno Setup compiled the Chinese `Yanami-Sub-0.1.0-rc.6.post3-Setup.exe` successfully without Authenticode.
- Caught and corrected an empty first manifest announcement by regenerating only RC6.3 update assets with the release notes. Verified the resulting signature, notes, full-update selection, asset sizes and digests, all three SHA-256 sidecars, ProductVersion fields, and bundled frozen module.
- Committed RC6.3 as `b88921e`, pushed it to `origin/main`, and pushed annotated tag `v0.1.0-rc.6.post3` pointing to that commit.
- Published the public Yanami Sub 0.1.0 RC6.3 prerelease with eight assets. GitHub reports all expected assets at the tagged download URLs; each uploaded size and SHA-256 matches the local build, release notes match the signed announcement, and the release is not a draft.
- Started the download reliability/speed follow-up at the user's request. Read the current plan and prior findings, checked FineSub upstream before edits (still v0.5.1), and kept the working tree's tracked files clean. No release is requested for this follow-up.
## 2026-09-23 dependency download follow-up

- Confirmed FineSub upstream remains v0.5.1; no merge.
- Pinned the desktop uv bootstrap to official 0.12.17 with published size/SHA-256, leaving FineSub's own runtime manifest and dependency locks unchanged.
- Added proxy-to-direct network retry, automatic official-to-China mirror retry, and explicit source/transport logs; pause, local storage errors, forced source choice and canonical integrity errors are excluded from inappropriate retry.
- Cleared stale bootstrap ZIP progress at AI dependency stage; added bilingual note and expandable live install log.
- Focused backend tests passed: 34 tests. Initial sandboxed pytest could not create a temp directory; the identical suite passed with approved local execution.
- Confirmed the official uv 0.12.17 Windows x64 ZIP asset on GitHub API: 17,906,210 bytes, SHA-256 `a252121d5b59398fcb137c6ea448176459a44010f33f67e0072305a637119ca7`.
- Installed uv 0.12.17 only in the untracked development virtual environment and ran offline dry-runs against the canonical and temporary normalized China lock. The first raw China-lock attempt failed on its dotted filename; the normalized run passed.
- Added bounded source samples for slow-but-not-failing connections, including a TUNA reachability guard, with forced-source bypass and pause safety.
- Full backend reached 420 passes and one unrelated transient Windows `os.replace` denial in the updater test; that exact updater test passed in a new temp root. The subsequent full backend run passed 423 tests; frontend build passed, 95 frontend tests passed, and 42 script tests passed.
- Final optional-probe safeguards passed another complete backend run: 425 tests. Final frontend tests passed again (95), static build remained successful, and `git diff --check` reported no whitespace error. A small live probe from this machine chose the China lock, but sustained 2.6 GB performance has not been benchmarked in representative mainland and overseas networks.
- An existing local torch wheel candidate now bypasses the unnecessary network speed sample; the existing SHA-256 validation in `local_lock` still decides whether the local file may actually be installed. The final backend suite passed 426 tests.

## 2026-09-23 RC6.4 release

- Rechecked FineSub upstream before release edits: latest tag and main remain v0.5.1. Remote Yanami Sub main matches local RC6.3 commit, and RC6.4 has no existing tag or Release.
- Set all authoritative version surfaces to `0.1.0-rc.6.post4`; added release notes and RC6.3 to bundled update history. RC6.4 will use a complete online update package because the frozen launcher changed.
- Release-grade checks passed: 468 Python tests (backend plus release scripts), 95 frontend tests, TypeScript typecheck, and static WebView export build. A first Python run hit the known transient Windows staging rename denial in one updater test; a fresh full run passed.
- Built the RC6.4 frozen application, app/full update ZIPs, signed beta manifest, and Simplified Chinese Inno Setup installer without Authenticode. Verification is underway before upload.
- Verified the signed beta manifest against the pinned public key, nonempty RC6.4 announcement, and full-package selection for RC5 and RC6.3. App/full archive sizes, SHA-256 sidecars, and required static entrypoint all match the manifest.
- Verified the installer and updater ProductVersion are RC6.4, `manual_wheels` is frozen inside the launcher, the installer's SHA-256 is recorded, and Authenticode remains intentionally unsigned.
- Committed RC6.4 as `b6c081a`, pushed it to `origin/main`, and published annotated tag `v0.1.0-rc.6.post4` on the same commit.
- Published the public Yanami Sub 0.1.0 RC6.4 prerelease with eight assets. GitHub reports all eight uploaded sizes and SHA-256 digests equal the local verified files; the release is not a draft and is marked prerelease.

## 2026-09-23 RC6.4 torch stall investigation

- Read the user's complete displayed log and pause/resume screenshot, rechecked upstream FineSub tags (latest remains v0.5.1), and confirmed the working tree has no tracked changes. Investigation is diagnostic only.
- Traced the resource UI through the install manager into FineSub's uv subprocess: uv supplies no per-wheel byte telemetry, pause terminates the subprocess and restarts staging, and automated fallbacks require a terminal network error. Confirmed upstream uv documentation and found existing persistent `.part` downloader as a possible future targeted fix.
- Diagnostic conclusion: the transcript proves the 2.6 GiB torch wheel remains the unfinished item, not that the whole application is deadlocked. Proposed immediate route switch or SHA-verified manual wheel placement, and a separate small follow-up that reuses the existing resumable downloader rather than inventing segmentation. No product code or release changed.

## 2026-09-23 RC6.5 release

- Rechecked FineSub upstream (still v0.5.1), remote `main`, existing RC6.4 Release, and the trusted Ed25519 private key before release edits. No upstream merge and no Authenticode certificate work.
- Versioned the tested local-wheel path fix, one-package uv cache repair, and duplicate-log removal as `0.1.0-rc.6.post5`; updated Chinese docs, release notes, and bundled RC6.4 history.
- Release-grade tests passed: 470 Python and 95 frontend tests, TypeScript typecheck, and static WebView build/validation. First sandboxed test runs hit Windows temp access and Node spawn denials; approved reruns passed.
- Built frozen launcher/updater, Chinese Setup, app/full ZIPs, SHA-256 sidecars, and Ed25519-signed beta update manifest. The manifest signature and all archive hashes match; ZIP CRC checks pass; bundled launcher includes `manual_wheels`; install and launcher ProductVersion are RC6.5.
- Confirmed RC4, RC5, and RC6.4 select the full update package. Setup and launcher are unsigned by Authenticode as intended. Publishing remains.
- Committed RC6.5 as `923ec38`, atomically pushed `main` and annotated tag `v0.1.0-rc.6.post5`, and published the prerelease with eight assets. The final release's per-release assets API reports all eight as uploaded; every reported size and SHA-256 matches local artifacts.
- GitHub's repository-wide releases-list API still returns the new release with an empty `assets` array, even for an unauthenticated request matching the application's headers. This prevents existing clients from discovering the update, though the signed manifest and all assets exist. Tried editing/re-publishing metadata and reconstructing the new release (after confirming all download counts were zero); the list response remained empty. Do not claim in-app update discovery is available until GitHub's list response includes those assets or an updater fallback ships through a future route.
## 2026-09-23 RC6.9 release

- User requested RC6.9 after the model-download proxy refusal repair. FineSub upstream main/latest tag remain v0.5.1; local and remote Yanami Sub main match RC6.8, and RC6.9 tag/Release are vacant.
- Verified the existing Ed25519 update-signing key matches the public key pinned in shipped clients. No Authenticode signing is planned.
- Set the authoritative version surfaces to `0.1.0-rc.6.post9`, added release notes and a bilingual bundled announcement/history entry, and updated install guidance. The frozen launcher changed, so the online updater must offer a full package.
- Frontend regression passed 96/96 and TypeScript typecheck passed. Full Python regression is running.
- Full Python/scripts regression passed 485/485. The first build passed frontend tests, typecheck, static export, PyInstaller, and Inno Setup, but release verification caught an omitted new `network.py` from the app ZIP because the packager only copies Git-indexed backend files.
- Staged only `desktop/backend/common/network.py` to include it in the indexed build input, then rebuilt frozen app, update ZIPs, signed manifest, and Setup. Both app/full ZIPs now include the new module and exact edited source; ZIP CRC, SHA-256, Ed25519 signature, RC6.9 metadata, and RC6.8-to-full selection pass. The frozen EXE includes the new network and prefetch modules. Installer, launcher, and updater are intentionally not Authenticode-signed.
- Committed RC6.9 as `dfa149b`, atomically pushed `main` and annotated tag `v0.1.0-rc.6.post9`, then published the public prerelease. All eight remote attachments match local sizes and SHA-256 digests, and their public URLs now use the final tag. The application's own live beta updater fetcher found RC6.9, downloaded and verified its signed manifest, and selected the full package for RC6.8. Tracked working tree is clean.

## 2026-09-24 Hugging Face model-download warning fix

- Checked FineSub upstream main and latest tag: both remain v0.5.1 at `b9b2f10c80abd58ddff739b60461624f51c0789c`. No upstream merge or release requested.
- Traced model-prefetch logging and the shared worker environment. Anonymous public-model access is valid; optional free HF_TOKEN may help only when actual rate limiting occurs. Windows without symlinks still caches with ordinary files, possibly using more disk across revisions.
- Added a shared desktop child environment default that suppresses only Hugging Face's symlink warning, preserving both real symlink attempts and explicit user override. Replaced the verbose anonymous-access warning with a concise actionable log line; real HTTP/download errors remain visible. Updated Chinese and English model-cache guidance without adding a new credential store or cache format.
- Focused backend regression passed 60/60, full Python/scripts regression passed 488/488, frontend tests passed 96/96, TypeScript typecheck passed, production frontend build passed, and `git diff --check` passed. No multi-GB live model download was attempted; no version, push, or release was made.

## 2026-09-24 subtitle-processing log encoding

- New user request: inspect every subtitle-processing stage for Chinese, English, and other mojibake, repair the encoding path, and validate. Previous six tracked HF-warning edits remain in the working tree and must be preserved.
- Before any edits, rechecked FineSub upstream main `b9b2f10c80abd58ddff739b60461624f51c0789c` and latest release `v0.5.1`; no upstream merge is authorized. Repository and parent have no AGENTS.md.
- User added a frontend request in the same turn: outside New Task, show lower-right subtitle-processing progress ball, changing to the existing download-style green completion status. Rechecked upstream again before extending scope: main and latest release remain unchanged. Frontend-design and ui-animation guide reuse of the existing visual language and respect the app animation toggle/reduced motion.
- Fixed the shared desktop worker environment to pin `PYTHONIOENCODING=utf-8` after optional settings, preventing an inherited legacy codepage from corrupting task request and event/log pipes. Added a real child-process UTF-8 round trip for seven download/subtitle-stage samples, a six-stage reporter/event/file-log check, a mixed-language chunk writer check, and a batch event check.
- Reused the existing lower-right update ring classes for a background subtitle task; the ring is indeterminate and captions the current localized stage. The existing successful-task toast provides the green checked completion state, without a duplicate notification or new CSS. A fallback caption covers unexpected stage keys.
- Focused backend suite passed 71/71, complete Python/scripts suite passed 492/492, frontend suite passed 97/97, TypeScript typecheck passed, and production frontend build passed. Browser preview captured Chinese/light History and English/dark/motion-off Settings states for a simulated task; no real subtitle media/model processing was triggered.
- Read a real task log in place without changing it: MSVC's CP936 “正在创建库” lines were being irreversibly replaced when the parent decoded the shared pipe as UTF-8. Added native-byte preservation and Windows-codepage recovery at both single-task and batch protocol readers, while leaving UTF-8 JSONL events intact. The separate PyTorch `UnicodeDecodeError` during optional separator compilation is an upstream limitation and may still force its slower fallback; no unsupported runtime patch was applied.
- Final regression after this follow-up: 452 backend tests and 42 packaging-script tests passed (494 Python total), frontend 97/97, TypeScript typecheck, static production build, and `git diff --check`. The native/UTF-8 mixed-pipe test persists Chinese, English, Japanese, and accented Latin correctly. Light Chinese and dark English/motion-off progress-ball previews were inspected. No release, push, installation, or user-log rewrite was performed.

## 2026-09-24 task-log export and translation wait

- Started from the user's export failure and DSH-stage screenshot. Read the existing plan/worktree and rechecked FineSub upstream main/latest release, both still v0.5.1. Prior uncommitted fixes remain untouched. Tracing the export and actual task timeline before changing product code; no release requested.
- Found the export button invokes only a browser Blob download of the bounded UI log, not the native bridge or complete disk transcript. Identified the matching active task log read-only: DSH returned successfully after 201.093 seconds, then Gemma web search failed/retried HTTP 500/disconnects. The visible stage alone is not proof of a shell deadlock.
- Replaced Blob export with a native SAVE dialog and full owned task-log copy; running `.part` takes priority over a previous attempt's final log, and successful export reveals a localized open-location button. Focused bridge/job-manager tests passed 96/96 and frontend typecheck passed.
- User added explicit API-vs-Agent selection and ordered Agent failover while work was in progress. Inspected the exact final task outcome: subtitle files were generated; the later knowledge update failed. Read-only inspection of its DSH capsule stderr found `QUOTA: Insufficient Balance`, confirming a quota issue rather than a desktop freeze. Continue routing/skip-state work without mislabeling the completed correction.

## 2026-09-24 RC6.10 implementation and release preparation

- Added per-task API/Agent source choice for New Task and Batch. Automatic mode selects configured Gemini Free first, otherwise ordered local Agents; a private deterministic FineSub model group keeps resume stable without changing shared configuration.
- All-Agent correction exhaustion preserves raw subtitles and marks correction skipped; a failed optional post-correction knowledge update now preserves already-generated subtitles. Failed Agent candidates and bounded vendor errors are logged, including successful cross-Agent fallback. The real DSH capsule diagnosed quota exhaustion rather than a shell deadlock.
- Repaired full task-log export with a native save dialog and post-export open-location action. Prior pending HF-warning, UTF-8/native-log, and background subtitle-progress improvements are included in the same release scope.
- Upstream main remains FineSub v0.5.1 at `b9b2f10c80abd58ddff739b60461624f51c0789c`; no merge. Remote Yanami Sub main matches the existing RC6.9 tag and RC6.10 tag/Release are vacant. Existing Ed25519 key matches pinned public key.
- RC6.10 release-grade regression passed: 510 Python/script tests, 98 frontend tests, TypeScript typecheck, and static frontend build. Built frozen Windows application, app/full ZIPs, Ed25519-signed beta manifest, and Chinese Setup.
- Independently verified manifest signature and notes, archive sizes/SHA-256/CRC, packaged source-byte equality, no Node runtime in ZIPs, RC6.9-to-full selection, installer sidecar SHA-256, and RC6.10 ProductVersion on Setup/launcher/updater. Authenticode remains intentionally unsigned. Commit/push/publish remain.
- Committed RC6.10 as `f7356ca`, atomically pushed `main` and annotated `v0.1.0-rc.6.post10`, then created a draft prerelease with eight assets. All eight remote asset sizes/digests matched local files before publication.
- Published the public prerelease and confirmed its notes, tag, prerelease state, eight assets, and remote tag/main commit. A read-only live `GitHubUpdateService.check()` using an RC6.9 beta client configuration discovered RC6.10, validated the signed manifest, and selected the full package. Tracked worktree is clean. The actual quota-limited DSH service was not exercised end-to-end on this host; regression tests cover that recovery branch.

## 2026-09-24 RC6.10 replacement patch

- User authorized fixing the API-model window regression and replacing the existing RC6.10 release without a version bump. Rechecked FineSub upstream main; still v0.5.1 at `b9b2f10c80abd58ddff739b60461624f51c0789c`.
- Confirmed the current public RC6.10 prerelease has eight assets and the desktop bug binds the search-only Gemma target into a correction group. Same-version installed clients will require manual overwrite because version comparison will not offer this replacement in-app.
- Restricted dynamic API candidates to FineSub's correction-capable/basic rosters. This also excludes other catalog-only free models that FineSub deliberately does not bind to correction, while keeping Gemma's separate web-search path. Added free/paid/automatic preflight regression cases and updated RC6.10 notes plus bilingual bundled history.
- Focused model-source tests pass (7/7); complete Python/scripts regression passes (513/513), frontend tests pass (98/98), and frontend typecheck passes. Build/asset verification follows.
- Rebuilt the RC6.10 static frontend, frozen launcher/updater, app/full ZIPs, signed beta manifest, and Inno Setup installer. Independently verified the manifest against the pinned public key, nonempty updated notes, SHA-256 sidecars, ZIP CRC, exact packaged route source, RC6.9-to-full selection, and no update offer at the same RC6.10 version.
- Downloaded the existing public RC6.10 Release's eight assets into a version-specific local backup and verified every backup size and SHA-256 against GitHub metadata before any remote replacement.
- Committed the patch as `22095e6`, pushed `main`, safely moved the existing `v0.1.0-rc.6.post10` annotated tag to that commit using a tag-specific lease, and replaced the Release's eight assets while it was a draft. Updated its notes and republished the same RC6.10 prerelease.
- Final public verification: all eight asset sizes/SHA-256 digests and release notes match the local verified build; remote `main` and the peeled RC6.10 tag both point to `22095e6`. The application's real live update checker on RC6.9 finds RC6.10, validates the signed manifest, and selects `full`. Existing RC6.10 clients need manual overwrite; no version bump was made.

## 2026-09-24 RC6.10 still reports the old route

- User provided an eight-target API attempt order ending in `gemini-free-gemma-4-31b` and dynamic group `yanami-source-443bff1dc2b76abf`, exactly the pre-patch route. FineSub upstream main is still `b9b2f10c80abd58ddff739b60461624f51c0789c`; the corrected RC6.10 Release remains public with eight assets. Investigating the actual installed/running copy before another code change.
- Read-only comparison found the running G: installation's launcher, updater, and route module match the original RC6.10 full package byte-for-byte. Its cached old ZIP was downloaded at 15:44 and applied at 16:25, after the patched public assets were republished at 16:17. The current install is therefore stale; the application did not execute the patched code.
- No product code, user installation, task data, or GitHub release was changed during this investigation. Prepared a fresh locally verified Setup hash and exact manual overwrite path. A same-version in-app retry cannot deliver this patch; an RC6.11 version bump would require a new user decision.
