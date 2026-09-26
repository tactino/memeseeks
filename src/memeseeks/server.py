"""HTTP API + static PWA over one library."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import io
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .albums import CollectionError
from .inbox import MAX_IMAGE_BYTES, InboxError
from .library import LibraryError
from .review import ReviewError
from .search import EmptyLibrary
from .settings import SettingsError

WEB = Path(__file__).parent / "web"
USERSCRIPT = Path(__file__).parent / "browser" / "memeseeks.user.js"
POPCAT = WEB / "popcat.js"
TOKEN_COOKIE = "memeseeks_token"
INBOX_KEY_HEADER = "x-memeseeks-key"
MAX_INBOX_BODY = MAX_IMAGE_BYTES * 4 // 3 + 64 * 1024  # base64 image plus a little metadata
# mimetypes misses some of these on Windows; Web Share rejects files typed application/octet-stream.
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
               ".webp": "image/webp", ".bmp": "image/bmp", ".heic": "image/heic", ".heif": "image/heif"}


async def _json_body(request: Request) -> dict:
    """The body of a request that changes something. JSON only: a page on another site cannot send that
    here (its CORS preflight is never granted), so it cannot change your library behind your back."""
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(415, "send JSON")
    try:
        body = json.loads(await request.body())
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"bad request: {exc}") from exc
    if not isinstance(body, dict):
        raise HTTPException(400, "bad request: send an object")
    return body


def _ids(body: dict) -> list[str]:
    ids = body.get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise HTTPException(400, "bad request: ids must be a list of strings")
    return ids


def _with_urls(items: list[dict]) -> list[dict]:
    return [dict(m, image=f"/api/image/{m['id']}", thumb=f"/api/thumb/{m['id']}") for m in items]


def create_app(service, token: str | None = None, online=None, inbox=None, indexer=None, warmup=None,
               phone=None, lan: bool = False) -> FastAPI:
    """lan: this app is the one 手机访问 serves on the LAN address (see phone.py), behind the token."""
    app = FastAPI(title="memeseeks", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service

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
            if (request.url.path.startswith("/api/") and request.url.path not in ("/api/inbox", "/api/inbox/albums")
                    and not _authorized(request)):
                return JSONResponse({"error": "需要口令：请扫电脑上「设置 → 手机访问」里的二维码打开"
                                              "（或者用 memeseeks serve 打印的链接）"},
                                    status_code=401)
            response = await call_next(request)
            if request.url.path in ("/", "/index.html") and _matches(request.query_params.get("token")):
                response.set_cookie(TOKEN_COOKIE, token, httponly=True, samesite="strict")
            return response

    @app.middleware("http")  # added last, so it runs outermost: the 400s and 401s above get the headers too
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        # No other site may frame the app (a hidden frame could be clicked into 删除图集), sniff a response
        # into a script, or see a ?token= link in its Referer.
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.exception_handler(CollectionError)
    @app.exception_handler(SettingsError)
    async def _bad_change(request: Request, exc: Exception):
        return JSONResponse({"error": str(exc)}, status_code=404 if "no such" in str(exc) else 400)

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(EmptyLibrary)
    @app.exception_handler(LibraryError)
    async def _library_error(request: Request, exc: Exception):
        return JSONResponse({"error": str(exc)}, status_code=409)

    @app.get("/api/ready")
    def ready():
        # what the page shows under the header: the models (downloading on the first run, see warmup.py) and
        # the background indexing. Never reads the index, so it answers for an empty library too.
        found = warmup.status() if warmup is not None else {"state": "ready", "download": None, "error": None}
        return {**found, "indexing": indexer.status() if indexer is not None else None}

    @app.get("/api/search")
    def search(q: str = Query(..., min_length=1), maybe: int = Query(12, ge=0, le=60)):
        if warmup is not None and warmup.status()["state"] != "ready":
            raise HTTPException(503, "还在准备：模型加载好就能搜索")
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
            script = script.replace('"__MEMESEEKS_POPCAT__"', POPCAT.read_text(encoding="utf-8")
                                    .split("window.POPCAT = ", 1)[1].rstrip().rstrip(";"))  # the cat's shapes
            # text/plain with nosniff, as raw.githubusercontent.com serves userscripts: a userscript manager
            # installs it from the .user.js link, but no web page can run it with <script src>, where
            # stand-in GM_* functions could catch the inbox key
            return Response(script, media_type="text/plain; charset=utf-8", headers={"Cache-Control": "no-store"})

        def _has_key(request: Request) -> bool:
            # Only the browser script knows this key. Ordinary web pages can't send a custom header
            # to this server at all (the CORS preflight fails), so they can't slip memes in.
            return hmac.compare_digest(request.headers.get(INBOX_KEY_HEADER, "").encode(), inbox.key().encode())

        @app.get("/api/inbox/albums")
        def inbox_albums(request: Request):
            # where the collector can put what it collects: 我喜欢 and your 图集 (names only)
            if not _has_key(request):
                return JSONResponse({"error": "wrong or missing inbox key: reinstall the browser script"}, status_code=401)
            return [{"id": a["id"], "name": a["name"]} for a in service.albums.all()]

        @app.post("/api/inbox")
        async def receive(request: Request):
            if not _has_key(request):
                return JSONResponse({"error": "wrong or missing inbox key: reinstall the browser script"},
                                    status_code=401)
            if int(request.headers.get("content-length") or 0) > MAX_INBOX_BODY:
                return JSONResponse({"error": "image too large"}, status_code=413)
            try:
                body = json.loads(await request.body())
                data = base64.b64decode(body.get("image", ""), validate=True)
                album = body.get("album")
                if album is not None:
                    if not isinstance(album, str):
                        raise TypeError("album must be a string")
                    service.albums.get(album)  # 404 before storing anything
                result = inbox.receive(data, body)
                if album is not None:
                    service.albums.add(album, [result["id"]])
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

    # ---------------- 图集, the meme page, settings, upload ----------------
    def _album_urls(a: dict) -> dict:
        return dict(a, cover=f"/api/thumb/{a['cover']}" if a.get("cover") else None)

    @app.get("/api/albums")
    def albums():
        return [_album_urls(a) for a in service.album_list()]

    @app.post("/api/albums")
    async def album_create(request: Request):
        return service.albums.create((await _json_body(request)).get("name"))

    @app.get("/api/albums/{cid}")
    def album(cid: str, sort: str = Query("new", pattern="^(new|old)$")):
        found = service.album(cid, sort=sort)
        return dict(found, items=_with_urls(found["items"]))

    @app.patch("/api/albums/{cid}")
    async def album_rename(cid: str, request: Request):
        return service.albums.rename(cid, (await _json_body(request)).get("name"))

    @app.delete("/api/albums/{cid}")
    def album_delete(cid: str):
        service.albums.delete(cid)
        return {"deleted": cid}

    @app.post("/api/albums/{cid}/add")
    async def album_add(cid: str, request: Request):
        ids = _ids(await _json_body(request))
        known = set(service.library.paths())
        return {"added": service.albums.add(cid, [i for i in ids if i in known])}

    @app.post("/api/albums/{cid}/remove")
    async def album_remove(cid: str, request: Request):
        return {"removed": service.albums.remove(cid, _ids(await _json_body(request)))}

    @app.get("/api/meme/{image_id}")
    def meme(image_id: str, similar: int = 1):
        found = service.meme(image_id, similar=bool(similar))
        if found is None:
            raise HTTPException(404, "no such meme")
        return dict(_with_urls([found])[0], similar=_with_urls(found["similar"]))

    @app.post("/api/memes/remove")
    async def memes_remove(request: Request):
        removed = service.remove_memes(_ids(await _json_body(request)))
        if indexer is not None:
            indexer.request()  # collected files moved to rejected/
        return {"removed": removed}

    @app.get("/api/settings")
    def settings_get():
        return service.settings.get()

    @app.put("/api/settings")
    async def settings_put(request: Request):
        return service.settings.update(await _json_body(request))

    if inbox is not None:
        @app.post("/api/upload")
        async def upload(request: Request, album: str | None = None):
            # an image body only (image/*): like JSON, a page on another site cannot send that here
            ctype = request.headers.get("content-type", "").split(";")[0].strip()
            if not ctype.startswith("image/"):
                raise HTTPException(415, "send the image itself (image/*)")
            if int(request.headers.get("content-length") or 0) > MAX_IMAGE_BYTES:
                raise HTTPException(413, "image too large")
            if album is not None:
                service.albums.get(album)  # 404 before storing anything
            try:
                found = inbox.receive(await request.body(), {"site": "上传"})
            except InboxError as exc:
                raise HTTPException(400, str(exc)) from exc
            service.review.mark_kept([found["id"]])  # you chose it: no 待确认
            if album is not None:
                service.albums.add(album, [found["id"]])
            if found["status"] == "added" and indexer is not None:
                indexer.request()
            return found

    @app.get("/api/today")
    def today():
        found = service.today()
        return _with_urls([found])[0] if found else None

    # ---------------- 来源文件夹 and custom.css ----------------
    def _sources():
        inbox_dir = str((service.library.root / "inbox").resolve())
        return [{"path": src, "exists": Path(src).is_dir(), "inbox": src == inbox_dir}
                for src in service.library.config()["sources"]]

    @app.get("/api/sources")
    def sources():
        return _sources()

    @app.post("/api/sources")
    async def sources_add(request: Request):
        folder = str((await _json_body(request)).get("path") or "").strip().strip('"')
        if not folder or not Path(folder).expanduser().is_dir():
            raise HTTPException(400, "没有这个文件夹：请填这台电脑上一个文件夹的完整路径")
        service.library.add_source(Path(folder).expanduser())
        if indexer is not None:
            indexer.request()
        return _sources()

    @app.post("/api/sources/remove")
    async def sources_remove(request: Request):
        folder = str((await _json_body(request)).get("path") or "")
        if inbox is not None and Path(folder).resolve() == inbox.folder.resolve():
            raise HTTPException(400, "采集收件箱由迷因捕手管理，不能移除")
        if not service.library.remove_source(folder):
            raise HTTPException(404, "no such source folder")
        if indexer is not None:
            indexer.request()
        return _sources()

    @app.get("/api/custom.css")
    def custom_css():
        # your own styles, loaded after the app's: <library>/custom.css (docs/design.md, Settings)
        path = service.library.root / "custom.css"
        css = path.read_text(encoding="utf-8") if path.is_file() else ""
        return Response(css, media_type="text/css; charset=utf-8", headers={"Cache-Control": "no-cache"})

    @app.get("/api/feed")
    def feed(album: str | None = None, meme: str | None = None, order: str = Query("new", pattern="^(new|old|shuffle)$"),
             seed: int = 0):
        ids = service.feed(album=album, meme=meme, order=order, seed=seed)
        if ids is None:
            raise HTTPException(404, "no such meme")
        return {"ids": ids}

    @app.post("/api/seen")
    async def seen(request: Request):
        return {"seen": service.mark_seen(_ids(await _json_body(request)))}

    # ---------------- 手机访问 (see phone.py) ----------------
    def _this_computer_only():
        if lan or phone is None:
            raise HTTPException(403, "只能在运行迷因捕手的这台电脑上改")

    @app.get("/api/phone")
    def phone_status():
        # the link and its token only for this computer; a phone learns that it is on, nothing more
        return phone.status(local=not lan) if phone is not None else {"available": False}

    @app.put("/api/phone")
    async def phone_set(request: Request):
        _this_computer_only()
        body = await _json_body(request)
        on, address = body.get("on"), body.get("address")
        if not isinstance(on, bool) or not (address is None or isinstance(address, str)):
            raise HTTPException(400, "bad request: on must be true or false, address a string")
        return await asyncio.to_thread(phone.set, on, address)  # starting a server takes a moment

    @app.post("/api/phone/rotate")
    async def phone_rotate(request: Request):
        _this_computer_only()
        await _json_body(request)  # JSON only, like every change: no other site can ask for it
        return await asyncio.to_thread(phone.rotate)

    @app.get("/api/phone/qr.svg")
    def phone_qr():
        _this_computer_only()
        url = phone.url()
        if not url:
            raise HTTPException(404, "手机访问没有开启")
        try:
            import segno
        except ImportError as exc:
            raise HTTPException(501, 'the QR code needs segno: pip install -e ".[serve]"') from exc
        buf = io.BytesIO()
        # whole pixels per module, the standard 4-module quiet zone, crisp edges: shown at its own size
        segno.make(url, error="m").save(buf, kind="svg", scale=5, border=4, dark="#161411", light="#ffffff", xmldecl=False)
        svg = buf.getvalue().replace(b"<svg ", b'<svg shape-rendering="crispEdges" ', 1)
        return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})

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
