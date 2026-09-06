#!/bin/bash
# Stop the old runtime before an upgrade, preserving the desired running state.
set -eu
if [ ! -f "${6:?Missing package path}/bin/service/Dockerfile" ]; then
  echo '<ERROR> Use the built Q-Brain LoxBerry ZIP.'
  exit 2
fi
folder="${3:?Missing plugin folder}"
case "$folder" in ''|*[!a-zA-Z0-9_-]*) exit 2 ;; esac
controller="/usr/local/lib/qbrain/$folder/control.py"
if [ -f "$controller" ]; then
  "$controller" prepare_upgrade || { echo '<ERROR> Q-Brain is busy or could not stop. Finish the operation and retry the upgrade.'; exit 2; }
fi
