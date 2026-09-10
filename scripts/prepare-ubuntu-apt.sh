#!/usr/bin/env bash
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
test "${RUNNER_OS:-}" = Linux
# Playwright downloads its pinned browser itself. The runner's unrelated Chrome
# package index must not break installation of signed Ubuntu dependencies.
for source in /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
  if [ -f "$source" ] && grep -q 'dl.google.com/linux/chrome' "$source"; then
    sudo mv -- "$source" "$source.disabled"
  fi
done
