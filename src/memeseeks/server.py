"""HTTP API + static PWA over one library."""

from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .library import LibraryError
from .online import OnlineError
from .search import EmptyLibrary

WEB = Path(__file__).parent / "web"
TOKEN_COOKIE = "memeseeks_token"
# mimetypes misses some of these on Windows; Web Share rejects files typed application/octet-stream.
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
               ".webp": "image/webp", ".bmp": "image/bmp", ".heic": "image/heic", ".heif": "image/heif"}


def _with_urls(items: list[dict]) -> list[dict]:
    return [dict(m, image=f"/api/image/{m['id']}", thumb=f"/api/thumb/{m['id']}") for m in items]


def create_app(service, token: str | None = None, online=None) -> FastAPI:
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
            if request.url.path.startswith("/api/") and not _authorized(request):
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

    @app.get("/api/online")
    def online_search(q: str = Query(..., min_length=1), n: int = Query(20, ge=1, le=50)):
        if online is None:
            return {"enabled": False, "hits": []}
        try:
            hits = online.search(q, n=n)
        except OnlineError as exc:
            return JSONResponse({"enabled": True, "provider": online.provider, "error": str(exc)}, status_code=502)
        return {"enabled": True, "provider": online.provider,
                "hits": [{"id": h.id, "title": h.title, "provider": h.provider,
                          "thumb": f"/api/online/img/{h.id}?v=thumb", "image": f"/api/online/img/{h.id}?v=full"}
                         for h in hits]}

    @app.get("/api/online/img/{hit_id}")
    def online_image(hit_id: str, v: str = Query("thumb", pattern="^(thumb|full)$"), download: int = 0):
        try:
            found = online.image(hit_id, v) if online is not None else None
        except OnlineError as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
        if found is None:
            raise HTTPException(404)
        data, ctype = found
        headers = {"Cache-Control": "max-age=3600"}
        if download:
            ext = {"image/png": "png", "image/gif": "gif", "image/webp": "webp"}.get(ctype, "jpg")
            headers["Content-Disposition"] = f'attachment; filename="{hit_id.replace(":", "-")}.{ext}"'
        return Response(data, media_type=ctype, headers=headers)

    @app.get("/api/rediscover")
    def rediscover(n: int = Query(12, ge=1, le=60)):
        return _with_urls(service.rediscover(n=n))

    @app.get("/api/status")
    def status():
        return service.status()

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
