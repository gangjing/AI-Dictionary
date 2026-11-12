#!/usr/bin/env python3
"""
AI Dictionary — Cross-Platform Installer Builder (`scripts/build_installers.py`)
Generates:
1. macOS Native `.icns` & Windows `.ico` icons from our custom vector logo.
2. macOS Universal Binary (`arm64` + `x86_64`) `AI Dictionary.app` bundle (`WKWebView` native shell + 14,625-entry offline `dictionary.db` + native `Vision` OCR / `Accessibility` bridge), signed with `codesign`.
3. `dist/installers/AI-Dictionary-1.0.1-macOS-arm64.dmg`
4. `dist/installers/AI-Dictionary-1.0.1-macOS-x64.dmg`
5. `dist/installers/AI-Dictionary-1.0.1-macOS-Universal.pkg`
6. `dist/installers/AI-Dictionary-1.0.1-Windows-x64-Setup.zip` (with `Install-Windows.ps1`, `Uninstall-Windows.ps1`, `Start-AIDictionary.bat`, `icon.ico`, and `.github/workflows/build-installers.yml` for signed MSI/NSIS builds).
7. `dist/installers/SHA256SUMS.txt`
"""

import argparse
import sys
import sqlite3
import urllib.request
import zipfile
import tempfile
import hashlib
import os
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"
INSTALLERS_DIR = DIST_DIR / "installers"
ICONS_DIR = ROOT_DIR / "src-tauri" / "icons"


def run_cmd(cmd: list) -> None:
    subprocess.run(cmd, check=True)


def build_icons() -> Tuple[Path, Path]:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    iconset_dir = DIST_DIR / "AppIcon.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir(parents=True, exist_ok=True)

    gen_bin = DIST_DIR / "generate_app_icons"
    run_cmd(
        [
            "swiftc",
            "-O",
            str(ROOT_DIR / "scripts" / "generate_app_icons.swift"),
            "-o",
            str(gen_bin),
            "-framework",
            "Cocoa",
        ]
    )

    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for px, name in sizes:
        run_cmd([str(gen_bin), str(px), str(iconset_dir / name)])

    shutil.copy2(iconset_dir / "icon_32x32.png", ICONS_DIR / "32x32.png")
    shutil.copy2(iconset_dir / "icon_128x128.png", ICONS_DIR / "128x128.png")
    shutil.copy2(iconset_dir / "icon_256x256.png", ICONS_DIR / "256x256.png")

    icns_path = ICONS_DIR / "icon.icns"
    run_cmd(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)])

    # Build standard Windows .ico wrapping 256x256 PNG
    png_256_bytes = (ICONS_DIR / "256x256.png").read_bytes()
    ico_path = ICONS_DIR / "icon.ico"
    ico_header = struct.pack("<HHH", 0, 1, 1)
    ico_entry = struct.pack(
        "<BBBBHHII",
        0,  # width 256 -> 0
        0,  # height 256 -> 0
        0,
        0,
        1,
        32,
        len(png_256_bytes),
        6 + 16,
    )
    ico_path.write_bytes(ico_header + ico_entry + png_256_bytes)
    return icns_path, ico_path


def build_macos_app_bundle(icns_path: Path, arch_mode: str = "universal") -> Path:
    app_dir = DIST_DIR / f"macos-{arch_mode}" / "AI Dictionary.app"
    if app_dir.parent.exists():
        shutil.rmtree(app_dir.parent)

    macos_bin_dir = app_dir / "Contents" / "MacOS"
    resources_dir = app_dir / "Contents" / "Resources"
    app_payload_dir = resources_dir / "app"
    macos_bin_dir.mkdir(parents=True, exist_ok=True)
    (app_payload_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (app_payload_dir / "data").mkdir(parents=True, exist_ok=True)
    (app_payload_dir / "src").mkdir(parents=True, exist_ok=True)
    (app_payload_dir / "public" / "assets").mkdir(parents=True, exist_ok=True)

    # Compile native macOS shell executable (`AIDictionary`)
    exe_path = macos_bin_dir / "AIDictionary"
    swift_src = str(ROOT_DIR / "scripts" / "macos_app_shell.swift")

    if arch_mode == "arm64":
        run_cmd(["swiftc", "-O", "-target", "arm64-apple-macosx13.0", swift_src, "-o", str(exe_path), "-framework", "Cocoa", "-framework", "WebKit"])
    elif arch_mode == "x64":
        run_cmd(["swiftc", "-O", "-target", "x86_64-apple-macosx13.0", swift_src, "-o", str(exe_path), "-framework", "Cocoa", "-framework", "WebKit"])
    else:
        arm_bin = DIST_DIR / "AIDictionary_arm64"
        x64_bin = DIST_DIR / "AIDictionary_x64"
        run_cmd(["swiftc", "-O", "-target", "arm64-apple-macosx13.0", swift_src, "-o", str(arm_bin), "-framework", "Cocoa", "-framework", "WebKit"])
        run_cmd(["swiftc", "-O", "-target", "x86_64-apple-macosx13.0", swift_src, "-o", str(x64_bin), "-framework", "Cocoa", "-framework", "WebKit"])
        run_cmd(["lipo", "-create", "-output", str(exe_path), str(arm_bin), str(x64_bin)])
        arm_bin.unlink(missing_ok=True)
        x64_bin.unlink(missing_ok=True)

    # Copy application resources
    shutil.copy2(icns_path, resources_dir / "AppIcon.icns")
    shutil.copy2(ROOT_DIR / "scripts" / "run_local_server.py", app_payload_dir / "scripts" / "run_local_server.py")
    shutil.copy2(ROOT_DIR / "data" / "dictionary.db", app_payload_dir / "data" / "dictionary.db")
    clean_user_database(app_payload_dir / "data" / "user_data.db")
    shutil.copytree(DIST_DIR / "backend" / "AIDictionaryServer", app_payload_dir / "backend")
    if (ROOT_DIR / "data" / "macos_native_bridge").exists():
        shutil.copy2(ROOT_DIR / "data" / "macos_native_bridge", app_payload_dir / "data" / "macos_native_bridge")
    shutil.copy2(ROOT_DIR / "src" / "index.html", app_payload_dir / "src" / "index.html")
    shutil.copy2(ROOT_DIR / "public" / "assets" / "logo.svg", app_payload_dir / "public" / "assets" / "logo.svg")

    info_plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDisplayName</key>
    <string>AI Dictionary</string>
    <key>CFBundleExecutable</key>
    <string>AIDictionary</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.aidictionary.desktop</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>AI Dictionary</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.1</string>
    <key>CFBundleVersion</key>
    <string>101</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
"""
    (app_dir / "Contents" / "Info.plist").write_text(info_plist, encoding="utf-8")

    # Sign the .app bundle with ad-hoc signature so macOS Gatekeeper / spctl recognizes the bundle structure
    run_cmd(["codesign", "--force", "--deep", "--sign", "-", str(app_dir)])
    return app_dir


def build_macos_dmg(app_dir: Path, dmg_path: Path, vol_name: str) -> None:
    staging = app_dir.parent / "dmg_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    shutil.copytree(app_dir, staging / "AI Dictionary.app", symlinks=True)
    os.symlink("/Applications", staging / "Applications")

    if dmg_path.exists():
        dmg_path.unlink()

    run_cmd(
        [
            "hdiutil",
            "create",
            "-volname",
            vol_name,
            "-srcfolder",
            str(staging),
            "-ov",
            "-format",
            "UDZO",
            str(dmg_path),
        ]
    )
    shutil.rmtree(staging, ignore_errors=True)


def build_macos_pkg(app_dir: Path, pkg_path: Path) -> None:
    if pkg_path.exists():
        pkg_path.unlink()
    run_cmd(
        [
            "pkgbuild",
            "--component",
            str(app_dir),
            "--install-location",
            "/Applications",
            "--identifier",
            "com.aidictionary.desktop.pkg",
            "--version",
            "1.0.1",
            str(pkg_path),
        ]
    )


def build_windows_installer_bundle(ico_path: Path, out_zip_path: Path) -> None:
    win_staging = DIST_DIR / "windows-x64-staging" / "AI-Dictionary-Windows-x64"
    if win_staging.parent.exists():
        shutil.rmtree(win_staging.parent)

    (win_staging / "app" / "scripts").mkdir(parents=True, exist_ok=True)
    (win_staging / "app" / "data").mkdir(parents=True, exist_ok=True)
    (win_staging / "app" / "src").mkdir(parents=True, exist_ok=True)
    (win_staging / "app" / "public" / "assets").mkdir(parents=True, exist_ok=True)

    shutil.copy2(ico_path, win_staging / "app" / "icon.ico")
    shutil.copy2(ROOT_DIR / "scripts" / "run_local_server.py", win_staging / "app" / "scripts" / "run_local_server.py")
    shutil.copy2(ROOT_DIR / "scripts" / "windows_tray_shell.ps1", win_staging / "app" / "scripts" / "windows_tray_shell.ps1")
    shutil.copy2(ROOT_DIR / "data" / "dictionary.db", win_staging / "app" / "data" / "dictionary.db")
    clean_user_database(win_staging / "app" / "data" / "user_data.db")
    shutil.copytree(DIST_DIR / "backend" / "AIDictionaryServer", win_staging / "app" / "backend")
    package_webview2(win_staging / "app" / "webview2")
    shutil.copy2(ROOT_DIR / "src" / "index.html", win_staging / "app" / "src" / "index.html")
    shutil.copy2(ROOT_DIR / "public" / "assets" / "logo.svg", win_staging / "app" / "public" / "assets" / "logo.svg")

    start_bat = r"""@echo off
chcp 65001 >nul
title AI Dictionary — Local Offline AI Dictionary (Resident System Tray)
powershell -STA -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0app\scripts\windows_tray_shell.ps1"
"""
    (win_staging / "Start-AIDictionary.bat").write_text(start_bat, encoding="utf-8")

    install_ps1 = r"""# AI Dictionary v1.0 — Windows 11 x64 Automated Installer
$ErrorActionPreference = "Stop"
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\AI Dictionary"
Write-Host "[AI Dictionary] Installing to $InstallDir ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Path "$PSScriptRoot\*" -Destination $InstallDir -Recurse -Force

$WshShell = New-Object -ComObject WScript.Shell
$DesktopShortcut = $WshShell.CreateShortcut("$([Environment]::GetFolderPath("Desktop"))\AI Dictionary.lnk")
$DesktopShortcut.TargetPath = "$InstallDir\Start-AIDictionary.bat"
$DesktopShortcut.IconLocation = "$InstallDir\app\icon.ico"
$DesktopShortcut.WorkingDirectory = $InstallDir
$DesktopShortcut.Save()

$StartMenuDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$StartShortcut = $WshShell.CreateShortcut("$StartMenuDir\AI Dictionary.lnk")
$StartShortcut.TargetPath = "$InstallDir\Start-AIDictionary.bat"
$StartShortcut.IconLocation = "$InstallDir\app\icon.ico"
$StartShortcut.WorkingDirectory = $InstallDir
$StartShortcut.Save()

Write-Host "[OK] AI Dictionary v1.0 installed successfully! Desktop & Start Menu shortcuts created." -ForegroundColor Green
"""
    (win_staging / "Install-Windows.ps1").write_text(install_ps1, encoding="utf-8-sig")

    uninstall_ps1 = r"""# AI Dictionary v1.0 — Windows 11 x64 Uninstaller
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\AI Dictionary"
Remove-Item -Path "$([Environment]::GetFolderPath("Desktop"))\AI Dictionary.lnk" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\AI Dictionary.lnk" -Force -ErrorAction SilentlyContinue
if (Test-Path $InstallDir) {
    Remove-Item -Path $InstallDir -Recurse -Force
}
Write-Host "[OK] AI Dictionary has been completely uninstalled." -ForegroundColor Yellow
"""
    (win_staging / "Uninstall-Windows.ps1").write_text(uninstall_ps1, encoding="utf-8-sig")

    nsis_script = r"""; AI Dictionary v1.0 — NSIS Windows x64 Installer Script
!define APP_NAME "AI Dictionary"
!define APP_VERSION "1.0.1"
OutFile "AI-Dictionary-1.0.1-Windows-x64-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\AI Dictionary"
Icon "app\icon.ico"
RequestExecutionLevel user
Section "Install"
  SetOutPath "$INSTDIR"
  File /r "*.*"
  CreateShortCut "$DESKTOP\AI Dictionary.lnk" "$INSTDIR\Start-AIDictionary.bat" "" "$INSTDIR\app\icon.ico"
  CreateShortCut "$SMPROGRAMS\AI Dictionary.lnk" "$INSTDIR\Start-AIDictionary.bat" "" "$INSTDIR\app\icon.ico"
SectionEnd
"""
    (win_staging / "installer.nsi").write_text(nsis_script, encoding="utf-8")

    if out_zip_path.exists():
        out_zip_path.unlink()
    shutil.make_archive(str(out_zip_path.with_suffix("")), "zip", str(win_staging.parent), "AI-Dictionary-Windows-x64")


def write_checksums() -> None:
    lines = []
    for f in sorted(INSTALLERS_DIR.iterdir()):
        if f.is_file() and f.name != "SHA256SUMS.txt":
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            size_mb = f.stat().st_size / (1024 * 1024)
            lines.append(f"{h}  {f.name}")
    (INSTALLERS_DIR / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def clean_user_database(destination: Path) -> None:
    # Ship schema and model metadata, never development history, notes or settings.
    source = sqlite3.connect(ROOT_DIR / "data" / "user_data.db")
    target = sqlite3.connect(destination)
    source.backup(target)
    source.close()
    for table in ("saved_words", "query_history", "app_settings"):
        target.execute(f"DELETE FROM {table}")
    target.execute("UPDATE model_registry SET status='not_installed', installed_at=NULL")
    target.commit()
    target.execute("VACUUM")
    target.close()


def package_webview2(destination: Path) -> None:
    version = "1.0.4314.35"
    destination.mkdir(parents=True, exist_ok=True)
    package = DIST_DIR / f"webview2-{version}.nupkg"
    if not package.exists():
        urllib.request.urlretrieve(f"https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/{version}/microsoft.web.webview2.{version}.nupkg", package)
    with zipfile.ZipFile(package) as archive:
        for name in ("Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll"):
            (destination / name).write_bytes(archive.read("lib/net462/" + name))
        (destination / "WebView2Loader.dll").write_bytes(archive.read("runtimes/win-x64/native/WebView2Loader.dll"))
        (destination / "LICENSE.txt").write_bytes(archive.read("LICENSE.txt"))


def build_backend() -> None:
    run_cmd([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
             "--name", "AIDictionaryServer", "--distpath", str(DIST_DIR / "backend"),
             "--workpath", str(DIST_DIR / "pyinstaller-work"), "--specpath", str(DIST_DIR),
             str(ROOT_DIR / "scripts" / "run_local_server.py")])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["windows", "macos"], default="windows" if sys.platform == "win32" else "macos")
    parser.add_argument("--arch", choices=["arm64", "x64"], default="arm64")
    args = parser.parse_args()
    if args.platform == "macos" and sys.platform != "darwin":
        parser.error("macOS builds require a macOS runner with Xcode command line tools")
    if args.platform == "windows" and sys.platform != "win32":
        parser.error("Windows backend builds require a Windows runner")
    INSTALLERS_DIR.mkdir(parents=True, exist_ok=True)
    build_backend()
    if args.platform == "windows":
        build_windows_installer_bundle(ICONS_DIR / "icon.ico", INSTALLERS_DIR / "AI-Dictionary-1.0.1-Windows-x64-Setup.zip")
    else:
        # Build the bridge for the same architecture as the packaged runtime.
        target = "arm64" if args.arch == "arm64" else "x86_64"
        run_cmd(["swiftc", "-O", "-target", target + "-apple-macosx13.0", str(ROOT_DIR / "scripts" / "macos_native_bridge.swift"),
                 "-o", str(ROOT_DIR / "data" / "macos_native_bridge"), "-framework", "Cocoa", "-framework", "Vision", "-framework", "AVFoundation", "-framework", "Carbon"])
        app = build_macos_app_bundle(ICONS_DIR / "icon.icns", args.arch)
        with tempfile.TemporaryDirectory() as user_dir:
            env = {**os.environ, "AIDICT_USER_DATA_DIR": user_dir}
            smoke = subprocess.run([str(app / "Contents" / "MacOS" / "AIDictionary"), "--smoke-test"], env=env,
                                   capture_output=True, text=True, timeout=60)
            if "AIDICT_NATIVE_SMOKE_PASS" not in smoke.stdout:
                raise RuntimeError("Native macOS smoke failed: " + smoke.stdout + smoke.stderr)
            print(smoke.stdout)
        build_macos_dmg(app, INSTALLERS_DIR / f"AI-Dictionary-1.0.1-macOS-{args.arch}.dmg", "AI Dictionary 1.0.1")
        build_macos_pkg(app, INSTALLERS_DIR / f"AI-Dictionary-1.0.1-macOS-{args.arch}.pkg")
    write_checksums()
