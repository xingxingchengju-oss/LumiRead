"""Local operator guide for supervised iPhone field trials. Starts only on request."""

import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONFIRMATIONS = {
    "double_tap": "我已观察五次独立双击，顺序为左、右、左、右、左，每段一次。",
    "single_tap": "我已观察在真实 iPhone 后摄取景区只点一次。",
    "silent": "我已在同场家长端开启静音，观察到手机显示静音，并在原取景位置实际双击一次。",
    "near_far": "我已在实物标记前靠近后挪远，标记持续可见，并在手机和家长端看到了距离提醒及恢复。",
    "dim_restore": "我已遮暗后恢复照明，并在手机和家长端看到了明暗提醒及恢复。",
}
PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>LumiRead 现场验收</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f4f2e8;color:#173729;font-family:system-ui,sans-serif;min-height:100vh;display:grid;place-content:center}
body[data-mode=active]{background:#19543d;color:white}main{width:min(85vw,870px)}h1{font-size:clamp(38px,6vw,82px);line-height:1.18;margin:0 0 .35em}p{font-size:clamp(20px,2.6vw,33px);line-height:1.5;margin:.4em 0}
output{font:600 48px ui-monospace,monospace;display:block;margin-top:.3em}button{font:600 21px system-ui;padding:.6em 1em;border-radius:.4em;background:#20503b;color:white;border:1px solid #20503b;margin:14px 10px 0 0;cursor:pointer}
#no{color:#20503b;background:transparent}#status{font-size:16px;margin-top:1em}button:focus-visible{outline:3px solid #ce7a20}</style></head>
<body><main><h1 id="title">正在准备现场验收</h1><p id="cue"></p><output id="clock"></output>
<div id="buttons"></div><p id="status" role="status"></p></main><script>
const basePath = location.pathname;
const byId = id => document.getElementById(id);
let renderedNonce = null;
let deadline = 0;
let finished = false;

function tick() {
  const seconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
  byId("clock").textContent = deadline ? seconds + " 秒" : "";
}

async function sendChoice(value, nonce) {
  for (const button of byId("buttons").children) button.disabled = true;
  try {
    const response = await fetch(basePath + "/action", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({nonce, value}),
    });
    if (!response.ok) throw Error();
  } catch {
    byId("status").textContent = "请查看当前步骤，必要时刷新页面。";
    renderedNonce = null;
  }
}

function render(state) {
  document.body.dataset.mode = state.mode;
  byId("title").textContent = state.title;
  byId("cue").textContent = state.cue;
  deadline = state.end;
  if (state.nonce !== renderedNonce) {
    renderedNonce = state.nonce;
    byId("buttons").replaceChildren();
    for (const [value, label] of state.actions) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      if (!value) button.id = "no";
      button.onclick = () => sendChoice(value, state.nonce);
      byId("buttons").appendChild(button);
    }
  }
  finished = state.mode === "finished";
  byId("status").textContent = "";
  tick();
}

async function poll() {
  try {
    const response = await fetch(basePath + "/state", {cache: "no-store"});
    if (!response.ok) throw Error();
    render(await response.json());
  } catch {
    byId("status").textContent = "正在连接本机计时页…";
  }
  if (!finished) setTimeout(poll, 200);
}
poll();
setInterval(tick, 100);
</script></body></html>"""


class TerminalGuide:
    def ready(self, title, cue):
        input(f"\n{title}\n{cue}\n确认使用 iPhone 16 Pro Max 并准备好后按 Enter。")

    def display(self, title, cue, seconds=0, mode="wait"):
        print(title, cue, f"（{seconds:g} 秒）" if seconds else "", flush=True)

    def window(self, title, action, cue, seconds):
        self.display(title, f"请先看清提示：{cue} 等「{action}」出现后操作。", 4)
        time.sleep(4)
        start = time.time()
        self.display(action, cue, seconds, mode="active")
        time.sleep(seconds)
        return [start, time.time()]

    def settle(self, seconds):
        self.display("本次操作结束", "请停手，等待延迟上传与采样回执。", seconds)
        time.sleep(seconds)

    def confirm(self, phase):
        return (
            input(CONFIRMATIONS[phase] + " 实际完成请输入 y，其他输入记为未完成：")
            .strip()
            .lower()
            == "y"
        )

    def finish(self, passed):
        self.display(
            "本轮完成", "本轮通过。" if passed else "本轮未达标，已保留观察记录。"
        )

    def close(self):
        pass


class BrowserGuide(TerminalGuide):
    def __init__(self):
        self.lock = threading.Lock()
        self.answered = threading.Event()
        self.answer = None
        self.state = {}
        self.path = "/" + secrets.token_urlsafe(20)
        self.opened = False
        guide = self

        class Handler(BaseHTTPRequestHandler):
            def reply(self, status, mime, body=b""):
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == guide.path:
                    self.reply(200, "text/html;charset=utf-8", PAGE.encode())
                elif self.path == guide.path + "/state":
                    with guide.lock:
                        body = json.dumps(guide.state).encode()
                    self.reply(200, "application/json", body)
                else:
                    self.reply(404, "text/plain")

            def do_POST(self):
                if self.path != guide.path + "/action":
                    return self.reply(404, "text/plain")
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    if not 0 < length <= 1024:
                        raise ValueError("Invalid action length")
                    action = json.loads(self.rfile.read(length))
                    nonce, choice = action["nonce"], action["value"]
                except (KeyError, ValueError, TypeError):
                    return self.reply(400, "text/plain")
                with guide.lock:
                    allowed = [v for v, _ in guide.state["actions"]]
                    if (
                        guide.answered.is_set()
                        or nonce != guide.state["nonce"]
                        or type(choice) is not bool
                        or choice not in allowed
                    ):
                        return self.reply(409, "text/plain")
                    guide.answer = choice
                    guide.answered.set()
                self.reply(200, "text/plain")

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def display(self, title, cue, seconds=0, mode="wait", actions=()):
        with self.lock:
            self.answered.clear()
            self.answer = None
            self.state = {
                "title": title,
                "cue": cue,
                "end": int(1000 * (time.time() + seconds)) if seconds else 0,
                "mode": mode,
                "actions": actions,
                "nonce": secrets.token_urlsafe(12),
            }
        if not self.opened:
            self.opened = True
            url = f"http://127.0.0.1:{self.server.server_port}{self.path}"
            print("Mac 现场准备页（等待点击后开始）", url, flush=True)
            webbrowser.open(url, new=1)

    def ready(self, title, cue):
        self.display(title, cue, actions=[(True, "iPhone 16 Pro Max 现场已准备好")])
        self.answered.wait()

    def confirm(self, phase):
        self.display(
            "确认现场动作",
            CONFIRMATIONS[phase],
            actions=[(True, "我已实际完成"), (False, "未完成，记录本轮")],
        )
        self.answered.wait()
        return self.answer

    def finish(self, passed):
        self.display(
            "本轮完成",
            "本轮通过，记录已保存。" if passed else "本轮未达标，已保留观察记录。",
            mode="finished",
        )
        time.sleep(1)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
