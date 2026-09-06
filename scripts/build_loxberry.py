"""Build a LoxBerry-ready ZIP; no duplicate backend source is maintained."""
import argparse
import configparser
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package_entries(root=ROOT):
    entries = {}
    for name in ('plugin.cfg', 'preinstall.sh', 'preroot.sh', 'postroot.sh'):
        entries[name] = root / name
    for directory in ('bin', 'daemon', 'uninstall', 'webfrontend', 'templates', 'icons'):
        for path in (root / directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                entries[path.relative_to(root).as_posix()] = path
    for name in ('Dockerfile', 'pyproject.toml', 'requirements.lock', '.dockerignore'):
        entries['bin/service/' + name] = root / name
    for path in (root / 'qbox').glob('*.py'):
        entries['bin/service/qbox/' + path.name] = path
    return entries


def build(destination, root=ROOT):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, source in sorted(package_entries(root).items()):
            executable = name in ('preinstall.sh', 'preroot.sh', 'postroot.sh', 'daemon/daemon', 'uninstall/uninstall',
                                  'bin/control.py', 'bin/healthcheck')
            info = zipfile.ZipInfo(name, (2026, 9, 6, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, source.read_bytes().replace(b'\r\n', b'\n'))
        with zipfile.ZipFile(root / 'vendor/hollama-ui.zip') as frontend:
            for entry in frontend.infolist():
                name = entry.filename
                if entry.is_dir(): continue
                if name.startswith('/') or '..' in Path(name).parts:
                    raise ValueError('Invalid frontend path')
                info = zipfile.ZipInfo('webfrontend/htmlauth/chat/' + name, (2026,9,6,0,0,0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, frontend.read(name))
    return destination


if __name__ == '__main__':
    metadata = configparser.ConfigParser()
    metadata.read(ROOT / 'plugin.cfg')
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / ('qbrain-loxberry-' + metadata['PLUGIN']['VERSION'] + '.zip'))
    args = parser.parse_args()
    print(build(args.output))
