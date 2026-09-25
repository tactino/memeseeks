"""HTTP API + static PWA over one library."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .inbox import MAX_IMAGE_BYTES, InboxError
from .library import LibraryError
from .review import ReviewError
from .search import EmptyLibrary

WEB = Path(__file__).parent / "web"
USERSCRIPT = Path(__file__).parent / "browser" / "memeseeks.user.js"
TOKEN_COOKIE = "memeseeks_token"
INBOX_KEY_HEADER = "x-memeseeks-key"
MAX_INBOX_BODY = MAX_IMAGE_BYTES * 4 // 3 + 64 * 1024  # base64 image plus a little metadata
# mimetypes misses some of these on Windows; Web Share rejects files typed application/octet-stream.
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
               ".webp": "image/webp", ".bmp": "image/bmp", ".heic": "image/heic", ".heif": "image/heif"}


def _with_urls(items: list[dict]) -> list[dict]:
    return [dict(m, image=f"/api/image/{m['id']}", thumb=f"/api/thumb/{m['id']}") for m in items]


def create_app(service, token: str | None = None, online=None, inbox=None, indexer=None) -> FastAPI:
    app = FastAPI(title="memeseeks", docs_url=None, redoc_url=None, openapi_url=None)

    def _matches(value: str | None) -> bool:
        return bool(value) and hmac.compare_digest(value.encode(), token.encode())

    def _authorized(request: Request) -> bool:
        # Any one right credential is enough: a stale cookie must not shadow the right link.
        bearer = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        return any(_matches(v) for v in (request.cookies.get(TOKEN_COOKIE), request.query_params.get("token"), bearer))

    if not token:
        # Without a token the server trusts localhost only; rejecting other Host headers stops a
        # DNS-rebinding page from reading the library through the user's browser.
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "::1"])
    if token:
        @app.middleware("http")
        async def _require_token(request: Request, call_next):
            # The page and its static files hold no data; every /api/* route (images included) does.
            # The inbox checks its own key (the browser script has that, not the token).
            if (request.url.path.startswith("/api/") and request.url.path != "/api/inbox"
                    and not _authorized(request)):
                return JSONResponse({"error": "token required: open the link printed by `memeseeks serve`"},
                                    status_code=401)
            response = await call_next(request)
            if request.url.path in ("/", "/index.html") and _matches(request.query_params.get("token")):
                response.set_cookie(TOKEN_COOKIE, token, httponly=True, samesite="strict")
            return response

    @app.exception_handler(EmptyLibrary)
    @app.exception_handler(LibraryError)
    async def _library_error(request: Request, exc: Exception):
        return JSONResponse({"error": str(exc)}, status_code=409)

    @app.get("/api/search")
    def search(q: str = Query(..., min_length=1), maybe: int = Query(12, ge=0, le=60)):
        found = service.search(q, maybe_k=maybe)
        return {"matches": _with_urls(found["matches"]), "maybe": _with_urls(found["maybe"])}

    @app.get("/api/online/config")
    def online_config():
        # Settings only: the page asks the provider itself and shows its images from there.
        return online.as_json() if online is not None else {"enabled": False}

    if inbox is not None:
        @app.get("/api/inbox/memeseeks.user.js")
        def userscript(request: Request):
            # Under /api/ like the library itself: with a token, only a signed-in browser gets the key.
            server = str(request.base_url).rstrip("/")
            script = USERSCRIPT.read_text(encoding="utf-8")
            script = script.replace('"__MEMESEEKS_SERVER__"', json.dumps(server))
            script = script.replace('"__MEMESEEKS_KEY__"', json.dumps(inbox.key()))
            return Response(script, media_type="text/javascript; charset=utf-8", headers={"Cache-Control": "no-store"})

        @app.post("/api/inbox")
        async def receive(request: Request):
            # Only the browser script knows this key. Ordinary web pages can't send a custom header
            # to this server at all (the CORS preflight fails), so they can't slip memes in.
            if not hmac.compare_digest(request.headers.get(INBOX_KEY_HEADER, "").encode(), inbox.key().encode()):
                return JSONResponse({"error": "wrong or missing inbox key: reinstall the browser script"},
                                    status_code=401)
            if int(request.headers.get("content-length") or 0) > MAX_INBOX_BODY:
                return JSONResponse({"error": "image too large"}, status_code=413)
            try:
                body = json.loads(await request.body())
                data = base64.b64decode(body.get("image", ""), validate=True)
                result = inbox.receive(data, body)
            except (json.JSONDecodeError, binascii.Error, AttributeError, TypeError) as exc:
                return JSONResponse({"error": f"bad request: {exc}"}, status_code=400)
            except InboxError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)
            if result["status"] == "added" and indexer is not None:
                indexer.request()
            return result

    @app.get("/api/review")
    def review_list():
        found = service.review_list()
        return {"pending": _with_urls(found["pending"]), "progress": found["progress"]}

    @app.post("/api/review")
    async def review_decide(request: Request):
        # JSON only: a page on another site can't send that here (its CORS preflight is never granted).
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return JSONResponse({"error": "send JSON"}, status_code=415)
        try:
            body = json.loads(await request.body())
            ids = body["ids"] if "ids" in body else [body["id"]]
            decision = body["decision"]
            if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                raise TypeError("ids must be a list of strings")
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            return JSONResponse({"error": f"bad request: {exc}"}, status_code=400)
        results = {}
        for image_id in ids:
            try:
                results[image_id] = service.decide(image_id, decision)
            except ReviewError as exc:
                results[image_id] = f"error: {exc}"
        if indexer is not None and any(r in ("rejected", "kept") for r in results.values()):
            indexer.request()  # a reject (or its undo) changed the inbox folder
        failed = [r for r in results.values() if r.startswith("error")]
        status = 400 if failed and len(failed) == len(results) else 200
        return JSONResponse({"results": results, "progress": service.review.progress()}, status_code=status)

    @app.get("/api/rediscover")
    def rediscover(n: int = Query(12, ge=1, le=60)):
        return _with_urls(service.rediscover(n=n))

    @app.get("/api/status")
    def status():
        found = service.status()
        if indexer is not None:
            found["indexing"] = indexer.status()
        return found

    @app.get("/api/image/{image_id}")
    def image(image_id: str, download: int = 0):
        path = service.path(image_id)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type=IMAGE_TYPES.get(path.suffix.lower()),
                            filename=path.name if download else None,
                            content_disposition_type="attachment" if download else "inline")

    @app.get("/api/thumb/{image_id}")
    def thumb(image_id: str, size: int = Query(384, ge=64, le=1024)):
        path = service.thumbnail(image_id, size=size)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})

    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    return app
