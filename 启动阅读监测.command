#!/bin/zsh
set -eu
cd -- "${0:A:h}"

base_url='http://127.0.0.1:8742'
page_url="$base_url/#reading"

monitor_ready() {
  local response
  response=$(curl --noproxy '*' --silent --fail --max-time 2 "$base_url/api/v1/eye-care/monitor") || return 1
  [[ "$response" == *'"ritw-monitor-'* ]]
}

open_page() {
  print -r -- "阅读监测页面  $page_url"
  open "$page_url" || print -u2 -- "请在浏览器中打开上面的地址。"
}

if monitor_ready; then
  print -- "LumiRead 已在运行。"
  open_page
  exit 0
fi

if lsof -nP -iTCP:8742 -sTCP:LISTEN >/dev/null 2>&1; then
  print -u2 -- "8742 端口已被占用，阅读监测接口尚未就绪。请检查占用端口的程序后重试。"
  exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
  print -u2 -- "缺少项目运行环境。请在项目目录运行 make bootstrap，再双击此脚本。"
  exit 1
fi
if [[ ! -f apps/web/dist/index.html ]]; then
  make web
fi

print -- "正在启动 LumiRead。演示期间请保持此终端窗口开启，按 Control+C 停止服务。"
(
  for attempt in {1..60}; do
    if monitor_ready; then
      open_page
      exit 0
    fi
    sleep 0.5
  done
  print -u2 -- "页面尚未就绪。请查看此窗口中的服务日志，稍后打开 $page_url"
) &
opener_pid=$!
trap 'kill "$opener_pid" 2>/dev/null || true' EXIT
.venv/bin/python scripts/desktop.py
