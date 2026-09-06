#!/bin/bash
set -eu
case "$(uname -m)" in
  aarch64|x86_64) ;;
  *) echo '<ERROR> Q-Brain requires a 64-bit aarch64 or x86_64 host.'; exit 2 ;;
esac
if ! /usr/bin/python3 -c 'import sys; assert sys.version_info >= (3, 9)' 2>/dev/null; then
  echo '<ERROR> Q-Brain requires host Python 3.9 or newer.'
  exit 2
fi
if [ ! -f "${6:?Missing package path}/bin/service/Dockerfile" ]; then
  echo '<ERROR> Install the built Q-Brain LoxBerry ZIP, not the GitHub source archive.'
  exit 2
fi
echo '<OK> Q-Brain package and host checks passed.'
