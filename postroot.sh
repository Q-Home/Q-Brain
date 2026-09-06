#!/bin/bash
set -eu
/usr/bin/python3 -I "${6:?Missing package path}/bin/install.py" \
  --home "${LBHOMEDIR:?Missing LoxBerry environment}" --folder "${3:?Missing plugin folder}"
