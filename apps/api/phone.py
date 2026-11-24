"""Application served exclusively through the public camera tunnel."""

import os
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from . import storage
from .main import API, app, capture_access, lifespan, protect

# Register only routes used by Camera and its pairing flow.
phone = FastAPI(openapi_url=None, lifespan=lifespan, redirect_slashes=False)
paths = {
    "/glasses",
    "/assets",
    "/vision",
    API + "/sessions/{sid}/telemetry/batch",
    API + "/sessions/{sid}/alerts",
    API + "/me",
    API + "/sessions/{sid}/join",
    API + "/sessions/{sid}/snapshot",
    API + "/sessions/{sid}/captures",
    API + "/sessions/{sid}/events",
    API + "/sessions/{sid}/ws",
}
phone.router.routes.extend(route for route in app.routes if getattr(route, "path", None) in paths)
phone.middleware("http")(protect)


async def gateway(scope, receive, send):
    if scope["type"] not in {"http", "websocket"}:
        return await phone(scope, receive, send)
    connection = HTTPConnection(scope)
    origin = os.environ.get("LUMIREAD_PUBLIC_ORIGIN", "")
    # The origin server listens on a private loopback socket behind cloudflared.
    if (
        not origin
        or connection.headers.get("host") != urlsplit(origin).netloc
        or connection.headers.get("x-forwarded-proto") != "https"
    ):
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        return await JSONResponse({"detail": "请使用家长页的 HTTPS 配对码。"}, 403)(
            scope, receive, send
        )
    scope = {
        **scope,
        "scheme": "https" if scope["type"] == "http" else "wss",
        "phone_only": True,
    }
    # Check the camera ticket before the multipart parser spools an upload to disk.
    if scope.get("method") == "POST" and scope["path"].endswith("/captures"):
        sid = scope["path"].split("/")[-2]
        try:
            with storage.transaction() as db:
                capture_access(db, HTTPConnection(scope), sid)
        except HTTPException as exc:
            return await JSONResponse({"detail": exc.detail}, exc.status_code)(
                scope, receive, send
            )
    await phone(scope, receive, send)
