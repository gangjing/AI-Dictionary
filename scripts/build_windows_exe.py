"""Build the native Windows setup EXE from the current sources, using portable NSIS."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
PAYLOAD = DIST / 'windows-x64-staging' / 'AI-Dictionary-Windows-x64'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--makensis', type=Path, required=True)
    parser.add_argument('--bootstrapper', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Build on Windows')
    # Verify staging remains under the workspace before the existing packager recreates it.
    assert PAYLOAD.resolve().is_relative_to(ROOT.resolve())
    subprocess.run([sys.executable, str(ROOT / 'scripts/build_installers.py'), '--platform', 'windows'], check=True)
    csc = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(csc), '/nologo', '/target:winexe', '/platform:x64',
                    '/reference:System.Windows.Forms.dll', '/win32icon:' + str(ROOT / 'assets/icons/icon.ico'),
                    '/out:' + str(PAYLOAD / 'AI Dictionary.exe'), str(ROOT / 'scripts/windows_launcher.cs')], check=True)
    lines = []
    for item in sorted((PAYLOAD / 'app').rglob('*')):
        if item.is_file():
            relative = str(item.relative_to(PAYLOAD))
            if any(c in relative for c in ('$', '"', '\n')):
                raise ValueError('Unsafe installer path: ' + relative)
            lines.append(f'Delete "$INSTDIR\\{relative}"')
    dirs = [PAYLOAD / 'app', *(p for p in (PAYLOAD / 'app').rglob('*') if p.is_dir())]
    for item in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        lines.append(f'RMDir "$INSTDIR\\{item.relative_to(PAYLOAD)}"')
    manifest = PAYLOAD / 'uninstall-manifest.nsh'
    manifest.write_text('\n'.join(lines), encoding='utf-8-sig')
    output = DIST / 'installers/AI-Dictionary-1.0.5-Windows-x64-Setup.exe'
    subprocess.run([str(args.makensis.resolve()), '/V3', '/DPAYLOAD=' + str(PAYLOAD),
                    '/DOUTPUT=' + str(output), '/DBOOTSTRAPPER=' + str(args.bootstrapper.resolve()),
                    '/DUNINSTALL_MANIFEST=' + str(manifest), str(ROOT / 'scripts/windows_installer.nsi')], check=True)
    output.with_suffix('.exe.sha256').write_text(hashlib.sha256(output.read_bytes()).hexdigest() + '  ' + output.name + '\n', encoding='utf-8')
    print(output)

if __name__ == '__main__':
    main()
