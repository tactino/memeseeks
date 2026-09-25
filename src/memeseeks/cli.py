"""memeseeks command line: add folders, search them, check status, evaluate queries."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .index import failure_counts
from .library import Library, LibraryError, Models, default_home
from .search import EmptyLibrary, Searcher


def _positive(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memeseeks", description="无情的梗图诱捕器 — find memes by what you remember.")
    p.add_argument("--version", action="version", version=f"memeseeks {__version__}")
    p.add_argument("--lib", help="library directory (default: $MEMESEEKS_HOME or ~/.memeseeks)")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="add a folder of memes and index it")
    a.add_argument("folder")
    v = a.add_mutually_exclusive_group()
    v.add_argument("--vlm", action="store_true", help="from now on also describe images with a local VLM (needs a GPU)")
    v.add_argument("--no-vlm", action="store_true", help="stop using the VLM for this library")
    a.add_argument("--retry-failed", action="store_true", help="redo images that failed a step last time")
    s = sub.add_parser("search", help="search the library")
    s.add_argument("query")
    s.add_argument("-k", type=_positive, default=10)
    s.add_argument("--json", action="store_true")
    sub.add_parser("status", help="show what is in the library")
    e = sub.add_parser("eval", help="score a queries.csv (query,expected files)")
    e.add_argument("csv")
    w = sub.add_parser("serve", help="open the web app for this library")
    _serve_options(w)
    r = sub.add_parser("run", help="add a folder, then serve (what the Docker image runs)")
    r.add_argument("folder")
    _serve_options(r)
    return p


def _serve_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach it from your phone (needs --token)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--token", default=os.environ.get("MEMESEEKS_TOKEN"), help="access token (or $MEMESEEKS_TOKEN)")


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
MIN_TOKEN_LENGTH = 16
EXAMPLE_TOKENS = {"replace-with-a-long-random-string", "change-me"}
_GENERATE = 'generate one with: python -c "import secrets; print(secrets.token_urlsafe(24))"'


def _exposure_problem(host: str, token: str | None) -> str | None:
    """Anything other than localhost puts your memes on the network: require a real token."""
    if host in LOCAL_HOSTS:
        return None
    if not token:
        return f"--host {host} makes your memes reachable from the network; add --token <secret> ({_GENERATE})"
    if token in EXAMPLE_TOKENS or len(token) < MIN_TOKEN_LENGTH:
        return f"that token is too weak (example value or under {MIN_TOKEN_LENGTH} characters); {_GENERATE}"
    return None


def _serve(lib: Library, models: Models, host: str, port: int, token: str | None) -> int:
    problem = _exposure_problem(host, token)
    if problem:
        return _fail(problem)
    try:
        import uvicorn

        from .server import create_app
    except ImportError:
        return _fail('the web app needs the serve extra: pip install -e ".[serve]"')
    from .search import EmptyLibrary as _Empty
    from .service import LibraryService

    service = LibraryService(lib, models)
    try:
        service.warm()  # load the index and models now, not on the first search
    except _Empty as exc:
        print(f"note: {exc}", file=sys.stderr)
    shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    print(f"memeseeks is at http://{shown}:{port}/" + (f"?token={token}" if token else ""))
    if host in ("0.0.0.0", "::"):
        print("from your phone use this computer's LAN address instead of 127.0.0.1; over plain http "
              "only 保存 works there — copy and share need localhost or HTTPS")
    uvicorn.run(create_app(service, token=token), host=host, port=port, log_level="warning")
    return 0


def _fail(message: str) -> int:
    print(f"memeseeks: {message}", file=sys.stderr)
    return 1


def _status(lib: Library, models: Models) -> None:
    cfg = lib.config()
    try:
        searcher = Searcher(lib, models)
    except EmptyLibrary:
        searcher = None
    print(f"library: {lib.root}")
    print(f"sources: {len(cfg['sources'])}")
    for source in cfg["sources"]:
        print(f"  {source}")
        if not Path(source).is_dir():
            print(f"  missing: {source} (its memes stay searchable until the next add)")
    print(f"images: {len(searcher.ids) if searcher else 0}")
    print(f"with text: {len(searcher.text) if searcher else 0}")
    print(f"vlm: {'on' if cfg['vlm'] else 'off'}")
    if lib.index_dir.exists():
        counts = failure_counts(lib.index_dir)
        print("failed: " + ", ".join(f"{stage} {n}" for stage, n in counts.items()))


def _add(lib: Library, models: Models, folder: str, vlm: bool = False, no_vlm: bool = False,
         retry_failed: bool = False) -> int:
    if not Path(folder).is_dir():
        return _fail(f"{folder} is not a folder")
    if vlm:
        try:
            models.get("vlm")  # load before saving the setting, so a failure leaves it off
        except Exception as exc:
            return _fail(f"cannot load the VLM ({type(exc).__name__}: {exc}); it stays off")
    lib.add_source(folder)
    if vlm or no_vlm:
        lib.set_vlm(vlm)
    report = lib.update(models, retry_failed=retry_failed)
    if report["images"] == 0:
        print(f"no images found in {folder} (jpg, png, gif, webp, bmp, heic); nothing to index")
    else:
        print(f"indexed {report['images']} images "
              f"({report['duplicates']} duplicates, {len(report['unreadable'])} unreadable skipped)")
    failed = {stage: n for stage, n in report["failed"].items() if n}
    if failed:
        detail = ", ".join(f"{stage} {n}" for stage, n in failed.items())
        print(f"{sum(failed.values())} image(s) failed a step ({detail}); they are still found through the "
              "other steps. Run `memeseeks add <folder> --retry-failed` to redo them.")
    if "vlm_error" in report:
        print(f"warning: VLM unavailable, descriptions skipped ({report['vlm_error']}); "
              "use --no-vlm to turn it off", file=sys.stderr)
    for missing in report["missing_sources"]:
        print(f"warning: source folder is gone: {missing}", file=sys.stderr)
    return 0


def _utf8_streams() -> None:
    """Windows encodes piped output as the ANSI code page (GBK); emit UTF-8 everywhere instead."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main(argv=None, models: Models | None = None) -> int:
    _utf8_streams()
    args = _parser().parse_args(argv)
    lib = Library(args.lib or default_home())
    models = models or Models()
    try:
        if args.cmd == "add":
            return _add(lib, models, args.folder, args.vlm, args.no_vlm, args.retry_failed)
        elif args.cmd == "run":
            problem = _exposure_problem(args.host, args.token)  # before an hour of indexing, not after
            if problem:
                return _fail(problem)
            return _add(lib, models, args.folder) or _serve(lib, models, args.host, args.port, args.token)
        elif args.cmd == "search":
            hits = Searcher(lib, models).search(args.query, k=args.k)
            if args.json:
                print(json.dumps([h.__dict__ for h in hits], ensure_ascii=False, indent=2))
            else:
                for n, h in enumerate(hits, 1):
                    snippet = h.text.replace("\n", " ")[:30]
                    print(f"{n:>2}. {h.path}" + (f"  「{snippet}」" if snippet else ""))
        elif args.cmd == "status":
            _status(lib, models)
        elif args.cmd == "serve":
            return _serve(lib, models, args.host, args.port, args.token)
        elif args.cmd == "eval":
            result = Searcher(lib, models).evaluate(args.csv)
            print(f"{result['n_queries']} labeled queries; {len(result['unlabeled'])} unlabeled: {result['unlabeled']}")
            if result["unknown_files"]:
                print(f"files not found: {result['unknown_files']}", file=sys.stderr)
            print("| route | R@1 | R@5 | MRR |\n|---|---|---|---|")
            for m, s in result["scores"].items():
                print(f"| {m} | {s['recall@1']:.2f} | {s['recall@5']:.2f} | {s['mrr']:.2f} |")
    except (EmptyLibrary, LibraryError) as exc:
        return _fail(str(exc))
    except OSError as exc:  # e.g. a CSV path that does not exist
        return _fail(f"{exc.strerror or exc}: {exc.filename or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
