"""Root installation hook. No Docker installation, model pull or start on install."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', required=True)
    parser.add_argument('--folder', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not re.fullmatch(r'[A-Za-z0-9_-]+', args.folder):
        raise SystemExit('Root and a valid plugin folder are required')
    home = Path(args.home).resolve(strict=True)
    if not (home / 'config/system').is_dir():
        raise SystemExit('Not a LoxBerry home directory')
    source = Path(__file__).resolve().parent
    target = Path('/usr/local/lib/qbrain') / args.folder
    # User-writable LoxBerry plugin files are never executed by Docker as root.
    target.mkdir(parents=True, exist_ok=True, mode=0o755)
    if target.is_symlink() or target.parent.is_symlink():
        raise SystemExit('Unexpected installation symlink')
    os.chown(target, 0, 0)
    os.chmod(target, 0o755)
    shutil.copytree(source / 'service', target / 'service', dirs_exist_ok=True)
    shutil.copyfile(source / 'control.py', target / 'control.py')
    (target / 'installation.json').write_text(json.dumps({'folder': args.folder, 'home': str(home)}), encoding='utf-8')
    for path in target.rglob('*'):
        if path.is_symlink():
            raise SystemExit('Symlinks are not allowed in the root runtime')
        os.chown(path, 0, 0)
        os.chmod(path, 0o755 if path.is_dir() or path.name == 'control.py' else 0o644)
    # Exact operations only: no arbitrary Python, Docker or shell sudo permissions.
    rules = '\n'.join(f'loxberry ALL=(root) NOPASSWD: {target}/control.py {action}' for action in
                      ('config', 'save', 'status', 'start', 'stop', 'pull', 'logs')) + '\n'
    rulefile = Path('/etc/sudoers.d') / ('qbrain-' + args.folder)
    temporary = rulefile.with_suffix('.new')
    temporary.write_text(rules, encoding='utf-8')
    os.chmod(temporary, 0o440)
    try:
        subprocess.run(['/usr/sbin/visudo', '-cf', str(temporary)], check=True, capture_output=True)
        temporary.replace(rulefile)
    finally:
        temporary.unlink(missing_ok=True)
    subprocess.run([str(target / 'control.py'), 'initialize'], check=True)
    health = home / 'bin/plugins' / args.folder / 'healthcheck'
    os.chmod(health, 0o755)
    print('<OK> Q-Brain installed. Existing settings and data have been preserved.')
    print('<INFO> Open Q-Brain, save settings, then start the services and download the model.')
    if not shutil.which('docker'):
        print('<WARNING> Docker is not installed. Install Docker Engine and Compose v2 on this host first.')
    restored = subprocess.run([str(target / 'control.py'), 'boot'], capture_output=True)
    if restored.returncode:
        print('<WARNING> Automatic service restore failed. Use Start on the plugin page after checking Docker.')


if __name__ == '__main__':
    main()
