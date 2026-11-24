"""Host-only parent UI, LAN HTTPS phone UI, and public CA download."""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from contextlib import ExitStack, closing
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(os.environ.get("LUMIREAD_VAR", ROOT / "var")).resolve()


def lan_ip():
    if os.getenv("LUMIREAD_LAN_IP"):
        return str(ipaddress.ip_address(os.environ["LUMIREAD_LAN_IP"]))
    if sys.platform == "darwin":
        for interface in ("en0", "en1"):
            out = subprocess.run(
                ["ipconfig", "getifaddr", interface],
                capture_output=True,
                text=True,
                check=False,
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            return probe.getsockname()[0]
    except OSError as exc:
        raise SystemExit(
            "Set LUMIREAD_LAN_IP to the Mac's Wi-Fi IPv4 address."
        ) from exc


def save_key(path, key):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )


def certs(ip):
    folder = BASE / "tls"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    now = datetime.now(UTC)
    keypath = folder / "ca.key"
    der = folder / "lumiread-ca.cer"
    if keypath.exists() and der.exists():
        ca_key = serialization.load_pem_private_key(keypath.read_bytes(), None)
        ca = x509.load_der_x509_certificate(der.read_bytes())
    else:
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "LumiRead Local Demo CA")]
        )
        ca = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
            .add_extension(
                x509.KeyUsage(
                    False, False, False, False, False, True, True, False, False
                ),
                True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False
            )
            .sign(ca_key, hashes.SHA256())
        )
        save_key(keypath, ca_key)
        der.write_bytes(ca.public_bytes(serialization.Encoding.DER))
    leaf = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca.subject)
        .public_key(leaf.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(hours=2))
        .not_valid_after(now + timedelta(days=60))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address(ip)), x509.DNSName("localhost")]
            ),
            False,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .add_extension(
            x509.KeyUsage(True, False, True, False, False, False, False, False, False),
            True,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    save_key(folder / "server.key", leaf)
    (folder / "server.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (folder / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    return der


def lan_endpoint(stack):
    ip = lan_ip()
    public_cert = certs(ip)
    data = public_cert.read_bytes()

    class CertificateDownload(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/lumiread-ca.cer":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/x-x509-ca-cert")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer((ip, 8744), CertificateDownload)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stack.callback(server.server_close)
    stack.callback(server.shutdown)
    return (
        f"https://{ip}:8743",
        {
            "ca": f"http://{ip}:8744/lumiread-ca.cer",
            "ca_sha256": hashlib.sha256(data).hexdigest(),
        },
        [
            "apps.api.main:app",
            "--host",
            ip,
            "--port",
            "8743",
            "--ssl-keyfile",
            str(public_cert.parent / "server.key"),
            "--ssl-certfile",
            str(public_cert.parent / "server.pem"),
        ],
        (),
    )


def stop_child(proc):
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def start_child(stack, cmd, **opts):
    proc = subprocess.Popen(cmd, cwd=ROOT, **opts)
    stack.callback(stop_child, proc)
    return proc


def public_endpoint(stack):
    tool = shutil.which("cloudflared") or str(ROOT / ".cache/bin/cloudflared")
    if not os.access(tool, os.X_OK):
        raise RuntimeError(
            "Install cloudflared, then run make demo-public again (see README)."
        )
    # Reserve the origin before publishing it; an unrelated local process cannot take it.
    listener = stack.enter_context(closing(socket.create_server(("127.0.0.1", 0))))
    port = listener.getsockname()[1]
    proc = start_child(
        stack,
        [
            tool,
            "tunnel",
            "--config",
            str(ROOT / "scripts/quick-tunnel.yml"),
            "--no-autoupdate",
            "--url",
            f"http://127.0.0.1:{port}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    announced = Queue()

    def read_output():
        origin = None
        for line in proc.stdout:
            match = re.search(
                r"\|\s*(https://[a-z0-9-]+[.]trycloudflare[.]com)\s*\|", line
            )
            if match:
                origin = match.group(1)
            if origin and "Registered tunnel connection" in line:
                announced.put(origin)
                origin = None
            elif " ERR " in line or "failed" in line.lower() or "error" in line.lower():
                print(line.strip(), file=sys.stderr, flush=True)
        announced.put(None)

    Thread(target=read_output, daemon=True).start()
    try:
        origin = announced.get(timeout=65)
    except Empty:
        origin = None
    if not origin:
        raise RuntimeError("Cloudflare did not establish a public connection.")
    return proc, (
        origin,
        {"ca": None, "ca_sha256": None},
        ["apps.api.phone:gateway", "--fd", str(listener.fileno())],
        (listener.fileno(),),
    )


def serve(public=False):
    os.umask(0o077)
    BASE.mkdir(mode=0o700, parents=True, exist_ok=True)

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    with ExitStack() as stack:
        record = BASE / "server.json"

        def clear_record():
            if (
                record.exists()
                and json.loads(record.read_text()).get("pid") == os.getpid()
            ):
                record.unlink()

        stack.callback(clear_record)
        # Reserve the admin port before touching runtime files of an existing demo.
        parent = stack.enter_context(closing(socket.create_server(("127.0.0.1", 8742))))
        children = []
        fallback = False
        if public:
            try:
                with ExitStack() as resources:
                    tunnel, endpoint = public_endpoint(resources)
                    stack.enter_context(resources.pop_all())
                children.append(tunnel)
            except (OSError, RuntimeError) as exc:
                print(
                    f"{exc} Starting local-network fallback.",
                    file=sys.stderr,
                    flush=True,
                )
                fallback = True
                public = False
        if not public:
            endpoint = lan_endpoint(stack)
        origin, cert_info, phone_args, phone_fds = endpoint
        env = {**os.environ, "LUMIREAD_PHONE_ORIGIN": origin, "LUMIREAD_VAR": str(BASE)}
        env["LUMIREAD_PUBLIC_ORIGIN"] = origin if public else ""
        uv = [sys.executable, "-m", "uvicorn", "--no-access-log", "--no-proxy-headers"]
        from apps.api.storage import initialize

        initialize()
        commands = [
            ([sys.executable, "-m", "apps.api.worker"], ()),
            (
                uv + ["apps.api.main:app", "--fd", str(parent.fileno())],
                (parent.fileno(),),
            ),
            (uv + phone_args, phone_fds),
        ]
        for cmd, fds in commands:
            children.append(start_child(stack, cmd, env=env, pass_fds=fds))
        info = {
            "parent": "http://127.0.0.1:8742/app",
            "phone": origin + "/glasses",
            "mode": "public" if public else "lan",
            "public_unavailable": fallback,
            **cert_info,
            "pid": os.getpid(),
        }
        tmp = record.with_suffix(".tmp")
        tmp.write_text(json.dumps(info, indent=2))
        tmp.replace(record)
        print(json.dumps(info, indent=2), flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(0.5)
        raise SystemExit(
            "A LumiRead process exited. Restart the demo in the preferred mode."
        )


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", action="store_true")
    try:
        serve(parser.parse_args().public)
    except KeyboardInterrupt:
        pass
