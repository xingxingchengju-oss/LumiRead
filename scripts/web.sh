#!/bin/sh
set -eu
runtime="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies"
if [ -x "$runtime/node/bin/node" ]; then
  export PATH="$runtime/node/bin:$PATH"
fi
if ! command -v pnpm >/dev/null && [ -x "$runtime/bin/fallback/pnpm" ]; then
  export PATH="$runtime/bin/fallback:$PATH"
fi
exec pnpm --dir apps/web "$@"
