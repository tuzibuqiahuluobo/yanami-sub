from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
INSTALLER = (
    REPO_ROOT / "desktop" / "installer" / "YanamiSub.iss"
)
BUILD_SCRIPT = REPO_ROOT / "desktop" / "scripts" / "build-installer.ps1"


def _installer_text() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def _build_script_text() -> str:
    return BUILD_SCRIPT.read_text(encoding="utf-8")


def test_installer_has_per_user_configurable_install_directory() -> None:
    script = _installer_text()
    assert "AppName=Yanami Sub" in script
    assert "DefaultDirName={localappdata}\\Programs\\Yanami Sub" in script
    assert "UsePreviousAppDir=no" in script
    assert "UsePreviousAppDir=yes" not in script
    assert "PrivilegesRequired=lowest" in script
    assert "DisableDirPage=no" in script


def test_installer_creates_shortcuts_and_can_launch_application() -> None:
    script = _installer_text()
    assert 'Name: "{autoprograms}\\Yanami Sub"' in script
    assert 'Name: "{autodesktop}\\Yanami Sub"' in script
    assert "Tasks: desktopicon" in script
    assert '#define AppExeName "Yanami Sub.exe"' in script
    assert 'Filename: "{app}\\{#AppExeName}"' in script
    assert "postinstall" in script


def test_installer_uses_branding_and_exact_output_name() -> None:
    script = _installer_text()
    assert '#define AppPublisher "tuzibuqiahuluobo"' in script
    assert "AppPublisher={#AppPublisher}" in script
    assert "SetupIconFile={#SetupIcon}" in script
    assert "UninstallDisplayIcon={app}\\Yanami Sub.exe" in script
    assert "OutputBaseFilename=Yanami-Sub-{#AppVersion}-Setup" in script
    assert "Compression=lzma2/ultra64" in script
    assert "SolidCompression=yes" in script


def test_installer_build_requires_a_valid_authenticode_signature_on_request() -> None:
    script = _build_script_text()
    assert "[switch]$RequireAuthenticode" in script
    assert "Get-YanamiSubCodeSigningCertificate" in script
    assert "Get-YanamiSubPackagedExecutables" in script
    assert "Set-YanamiSubAuthenticodeSignature" in script
    # The second call is after Inno produced the Setup executable.
    assert script.rfind("Set-YanamiSubAuthenticodeSignature") > script.index(
        'InstallerName = "Yanami-Sub-$Version-Setup.exe"'
    )


def test_installer_always_uses_bundled_chinese_language() -> None:
    # Inno Setup ships no Simplified Chinese, so probing the compiler's
    # Languages folder produced an English-only installer wherever the
    # community translation had not been dropped in by hand. Vendoring it is
    # what makes every build come out the same.
    installer = _installer_text()
    build_script = _build_script_text()
    assert "#ifndef ChineseLanguageFile" in installer
    assert 'Name: "chinesesimp"; MessagesFile: "{#ChineseLanguageFile}"' in installer
    assert (
        'ChineseLanguageFile = Join-Path $RepoRoot '
        '"desktop\\installer\\ChineseSimplified.isl"'
    ) in build_script
    assert '"/DChineseLanguageFile=$ChineseLanguageFile"' in build_script
    assert (
        Path(__file__).resolve().parents[2] / "installer" / "ChineseSimplified.isl"
    ).is_file()


def test_installer_uses_only_chinese_without_asking_which_language() -> None:
    # A second language lets automatic locale detection choose English on an
    # English Windows installation. One Chinese entry makes every build and
    # every locale deterministic without presenting a language picker.
    installer = _installer_text()
    languages = installer.split("[Languages]", 1)[1].split("[", 1)[0]
    entries = [line for line in languages.splitlines() if line.startswith("Name:")]

    assert "ShowLanguageDialog=no" in installer
    assert entries == [
        'Name: "chinesesimp"; MessagesFile: "{#ChineseLanguageFile}"'
    ]
    assert "compiler:Default.isl" not in installer
    assert "是否同时删除 Yanami Sub 已生成的字幕？" in installer
    assert "是否同时删除 FineSub 数据目录" in installer
    assert "Also delete the subtitles" not in installer
    assert "Also delete the FineSub data folder" not in installer


def test_installer_writes_the_installed_marker() -> None:
    # The marker is what separates installed copies (personal data in
    # %LOCALAPPDATA%\FineSub) from portable ones; only the installer may
    # create it -- update payloads never ship one and the full updater
    # preserves it.
    script = _installer_text()
    assert (
        "SaveStringToFile(ExpandConstant('{app}\\installed.marker')" in script
    )
    assert "ssPostInstall" in script


def test_rc3_removes_obsolete_finesub_desktop_entry_points() -> None:
    script = _installer_text()
    assert "[InstallDelete]" in script
    for obsolete in (
        "{app}\\FineSub Desktop.exe",
        "{app}\\updater\\FineSub Desktop Updater.exe",
        "{autoprograms}\\FineSub Desktop.lnk",
        "{autodesktop}\\FineSub Desktop.lnk",
    ):
        assert f'Type: files; Name: "{obsolete}"' in script


def test_uninstall_removes_only_what_can_be_rebuilt_without_asking() -> None:
    # Same split as `finesub uninstall`: rebuildable state goes, and the two
    # kinds that cannot be recreated -- finished subtitles and personal data --
    # are each asked about.
    script = _installer_text()
    for runtime_child in ("runtime", "models", "cache", "app", ".update"):
        assert (
            "DelTree(ExpandConstant('{app}\\" + runtime_child + "')"
        ) in script
    assert "DeleteFile(ExpandConstant('{app}\\installed.marker'))" in script
    assert "{app}\\tasks" in script
    assert "{localappdata}\\FineSub" in script
    assert script.count("MsgBox(") == 2
    assert "usPostUninstall" in script


def test_a_silent_uninstall_never_answers_yes_for_the_user() -> None:
    """Under /SUPPRESSMSGBOXES Inno answers a MsgBox with its default button.

    For MB_YESNO that default is Yes, so both prompts -- finished subtitles and
    the whole data folder, API keys and knowledge base included -- used to be
    agreed to on the user's behalf by anything running the uninstaller
    silently. The two things the uninstaller cannot recreate are exactly the
    two it must keep when nobody can be asked.
    """

    script = _installer_text()
    for subject in ("Subtitles", "PersonalData"):
        assert (
            f"if DirExists({subject}) and not UninstallSilent() then" in script
        ), f"the {subject} prompt is reachable during a silent uninstall"
    # Every prompt carries a guard: add a third one without it and these
    # diverge. The count is the invariant, not the number two.
    assert script.count("UninstallSilent()") == script.count("MsgBox(")


def test_installer_build_validates_required_application_files() -> None:
    script = _build_script_text()
    # Whole relative paths, not basenames: the manifest and the locks moved
    # out of `desktop/` in 2026-09, and a basename check kept passing while
    # the script still required them from a directory that no longer exists.
    for expected in (
        "Yanami Sub.exe",
        "app\\current.json",
        "src\\finesub_bootstrap\\runtime-manifest.json",
        "src\\finesub_bootstrap\\download-sources.json",
        "src\\finesub_bootstrap\\pylock.win-py312.toml",
        "src\\finesub_bootstrap\\pylock.win-py312.cn.toml",
    ):
        assert expected in script
    assert "ISCC.exe" in script
    assert "Yanami-Sub-$Version-Setup.exe" in script
