"""HTTP layer. Run: python run.py   (or: python -m uvicorn jal_drishti.api:app --port 8000)"""
import os
from collections import Counter
from typing import Dict, Iterable, Optional

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .brief import build_brief
from .config import CORS_ENV, CRITERIA_SOURCE, DEFAULT_CPCB_CLASS, resolve_frontend_dir
from .coverage import build_coverage, site_coverage
from .criteria import available_classes, criteria_for_class, criteria_map, criterion_to_dict
from .data_loader import DataFileError
from .filters import FILTER_FIELDS, FilterError, parse_cpcb_class, parse_filters, parse_int, resolve_site
from .ranking import assess_one_site, rank_ghats, ranking_to_dict
from .serializers import caveats_for, ghat_info, reading_with_comparison
from .store import DataStore
from .summary import build_summary

SERVICE = "jal-drishti-backend"
MAX_PAGE_SIZE = 2000


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or {}


def _error(status: int, code: str, message: str, details: Optional[dict] = None) -> JSONResponse:
    return JSONResponse(status_code=status,
                        content={"error": {"status": status, "code": code, "message": message, "details": details or {}}})


def _query(request: Request, allowed: Iterable[str]) -> Dict[str, str]:
    allowed = set(allowed)
    keys = list(dict.fromkeys(request.query_params.keys()))
    unknown = [k for k in keys if k not in allowed]
    if unknown:
        raise ApiError(400, "unknown_query_parameter", f"Unknown query parameter(s): {', '.join(unknown)}.",
                       {"allowed": sorted(allowed)})
    return {k: ",".join(request.query_params.getlist(k)) for k in keys}


def _q(desc: str):
    return Query(None, description=desc)


D_YEAR = "Year(s), comma-separated, e.g. 2024 or 2023,2025."
D_FEST = "Ganesh and/or Durga (case-insensitive)."
D_PHASE = "pre, during, after (comma-separated)."
D_SITE = "Ghat name or site_id from /api/ghats (comma-separated)."
D_PARAM = "Parameter name, e.g. BOD or 'Dissolved oxygen' (comma-separated)."
D_CLASS = f"CPCB class for comparisons (default {DEFAULT_CPCB_CLASS})."


def create_app(data_dir=None) -> FastAPI:
    store = DataStore(data_dir)
    app = FastAPI(title="Jal Drishti API", version=__version__,
                  description="Bhopal visarjan-ghat readings (MPPCB 2023–2025) compared with CPCB criteria. "
                              "Read-only, local, CSV-backed.")
    app.state.store = store
    origins = [o.strip() for o in os.environ.get(CORS_ENV, "*").split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["*"])

    @app.exception_handler(ApiError)
    async def _api_err(_r, exc: ApiError):
        return _error(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(FilterError)
    async def _filter_err(_r, exc: FilterError):
        return _error(400, "invalid_query", exc.message, exc.to_dict())

    @app.exception_handler(DataFileError)
    async def _data_err(_r, exc: DataFileError):
        return _error(503, "data_unavailable", exc.message, exc.to_dict())

    @app.exception_handler(StarletteHTTPException)
    async def _http_err(_r, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return _error(404, "not_found", "No such endpoint. See /docs.")
        return _error(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _val_err(_r, exc: RequestValidationError):
        return _error(400, "invalid_request", "Request could not be validated.",
                      {"errors": [{"loc": list(e.get("loc", ())), "msg": e.get("msg")} for e in exc.errors()]})

    def meta(ds, filters=None, cls=None, sites=(), **extra):
        m = {"caveats": caveats_for(ds, sites)}
        if filters is not None:
            m["filters"] = filters.as_dict()
        if cls is not None:
            m["cpcb_class"] = cls
        m.update(extra)
        return m

    @app.get("/api/health", tags=["service"])
    def health():
        try:
            ds = store.get()
        except DataFileError as exc:
            return JSONResponse(status_code=503, content={"data": {
                "status": "error", "service": SERVICE, "version": __version__,
                "data_dir": str(store.data_dir), "error": exc.to_dict()}, "meta": {}})
        cat = ds.catalog
        return {"data": {"status": "ok", "service": SERVICE, "version": __version__,
                         "files": {"readings": ds.readings_path, "criteria": ds.criteria_path},
                         "row_counts": {"readings": len(ds.readings), "criteria": len(ds.criteria)},
                         "sites": len(cat.sites), "events": [{"year": y, "festival": f} for y, f in cat.events],
                         "loaded_at": ds.loaded_at}, "meta": {}}

    @app.get("/api/ghats", tags=["ghats"])
    def ghats(request: Request):
        _query(request, ())
        ds = store.get()
        sites = list(ds.catalog.sites)
        return {"data": [ghat_info(ds, s) for s in sites], "meta": meta(ds, sites=sites, count=len(sites))}

    @app.get("/api/readings", tags=["readings"])
    def readings(request: Request, year: Optional[str] = _q(D_YEAR), festival: Optional[str] = _q(D_FEST),
                 phase: Optional[str] = _q(D_PHASE), site: Optional[str] = _q(D_SITE),
                 parameter: Optional[str] = _q(D_PARAM), cpcb_class: Optional[str] = _q(D_CLASS),
                 limit: Optional[str] = _q(f"Page size 1–{MAX_PAGE_SIZE} (default {MAX_PAGE_SIZE})."),
                 offset: Optional[str] = _q("Rows to skip (default 0).")):
        q = _query(request, set(FILTER_FIELDS) | {"cpcb_class", "limit", "offset"})
        ds = store.get()
        f = parse_filters(q, ds.catalog)
        cls = parse_cpcb_class(q.get("cpcb_class"), available_classes(ds.criteria))
        lim = parse_int(q.get("limit"), "limit", MAX_PAGE_SIZE, 1, MAX_PAGE_SIZE)
        off = parse_int(q.get("offset"), "offset", 0, 0, None)
        rows = [r for r in ds.readings if f.matches(r)]
        cmap = criteria_map(ds.criteria, cls, ds.catalog.parameters)
        page = rows[off:off + lim]
        sc = Counter(r.measurement_status for r in rows)
        return {"data": [reading_with_comparison(r, cmap, cls) for r in page],
                "meta": meta(ds, f, cls, sorted({r.site for r in rows}), total=len(rows), returned=len(page),
                             limit=lim, offset=off,
                             status_counts={k: sc[k] for k in ("measured", "below_detection", "missing")})}

    @app.get("/api/criteria", tags=["criteria"])
    def criteria(request: Request, cpcb_class: Optional[str] = _q("One class (A–E). Omit for all.")):
        q = _query(request, {"cpcb_class"})
        ds = store.get()
        classes = available_classes(ds.criteria)
        sel = parse_cpcb_class(q.get("cpcb_class"), classes, default=None)
        measured = set(ds.catalog.parameters)
        out = []
        for c in ([sel] if sel else classes):
            crits = criteria_for_class(ds.criteria, c)
            cmap = criteria_map(ds.criteria, c, measured)
            out.append({"cpcb_class": c, "designated_best_use": crits[0].designated_best_use,
                        "default_for_comparisons": c == DEFAULT_CPCB_CLASS,
                        "criteria": [{**criterion_to_dict(x), "measured_in_dataset": x.dataset_parameter in measured}
                                     for x in crits],
                        "dataset_parameters_without_criterion": [p for p in ds.catalog.parameters if p not in cmap]})
        return {"data": {"default_class": DEFAULT_CPCB_CLASS, "selected_class": sel, "source": CRITERIA_SOURCE,
                         "classes": out,
                         "notes": ["Class B (organised outdoor bathing) is used by default for immersion ghats.",
                                   "Conductivity is in µS/cm, which equals micromhos/cm."]},
                "meta": meta(ds)}

    @app.get("/api/summary", tags=["summary"])
    def summary(request: Request, year: Optional[str] = _q(D_YEAR), festival: Optional[str] = _q(D_FEST),
                phase: Optional[str] = _q(D_PHASE), site: Optional[str] = _q(D_SITE),
                parameter: Optional[str] = _q(D_PARAM), cpcb_class: Optional[str] = _q(D_CLASS)):
        q = _query(request, set(FILTER_FIELDS) | {"cpcb_class"})
        ds = store.get()
        f = parse_filters(q, ds.catalog)
        cls = parse_cpcb_class(q.get("cpcb_class"), available_classes(ds.criteria))
        data = build_summary(ds, f, cls)
        return {"data": data, "meta": meta(ds, f, cls, data["scope"]["sites"])}

    @app.get("/api/coverage", tags=["summary"])
    def coverage(request: Request, year: Optional[str] = _q(D_YEAR), festival: Optional[str] = _q(D_FEST),
                 phase: Optional[str] = _q(D_PHASE), site: Optional[str] = _q(D_SITE),
                 parameter: Optional[str] = _q(D_PARAM)):
        q = _query(request, FILTER_FIELDS)
        ds = store.get()
        f = parse_filters(q, ds.catalog)
        data = build_coverage(ds, f)
        return {"data": data, "meta": meta(ds, f, None, [s["site"] for s in data["sites"]])}

    @app.get("/api/rankings", tags=["rankings"])
    def rankings(request: Request, year: Optional[str] = _q(D_YEAR), festival: Optional[str] = _q(D_FEST),
                 phase: Optional[str] = _q(D_PHASE), site: Optional[str] = _q(D_SITE),
                 parameter: Optional[str] = _q(D_PARAM), cpcb_class: Optional[str] = _q(D_CLASS)):
        q = _query(request, set(FILTER_FIELDS) | {"cpcb_class"})
        ds = store.get()
        f = parse_filters(q, ds.catalog)
        cls = parse_cpcb_class(q.get("cpcb_class"), available_classes(ds.criteria))
        data = ranking_to_dict(rank_ghats(ds, f, cls), ds)
        return {"data": data, "meta": meta(ds, f, cls, [r["site"] for r in data["rankings"]])}

    @app.get("/api/ghats/{site_id:path}/readings", tags=["ghats"])
    def ghat_readings(site_id: str, request: Request, year: Optional[str] = _q(D_YEAR),
                      festival: Optional[str] = _q(D_FEST), phase: Optional[str] = _q(D_PHASE),
                      parameter: Optional[str] = _q(D_PARAM), cpcb_class: Optional[str] = _q(D_CLASS)):
        q = _query(request, {"year", "festival", "phase", "parameter", "cpcb_class"})
        ds = store.get()
        name = resolve_site(site_id, ds.catalog)
        if name is None:
            raise ApiError(404, "ghat_not_found", f"No ghat matches {site_id!r}. Use a site_id from /api/ghats.",
                           {"available_ids": [i.site_id for i in ds.catalog.sites.values()]})
        f = parse_filters(q, ds.catalog, ("year", "festival", "phase", "parameter")).with_sites([name])
        cls = parse_cpcb_class(q.get("cpcb_class"), available_classes(ds.criteria))
        cmap = criteria_map(ds.criteria, cls, ds.catalog.parameters)
        rows = [r for r in ds.readings if f.matches(r)]
        return {"data": {"ghat": ghat_info(ds, name), "assessment": assess_one_site(ds, name, f, cls),
                         "coverage": site_coverage(ds, name, f),
                         "readings": [reading_with_comparison(r, cmap, cls) for r in rows]},
                "meta": meta(ds, f, cls, [name], total=len(rows))}

    @app.get("/api/brief", tags=["brief"])
    def brief(request: Request, year: Optional[str] = _q(D_YEAR), festival: Optional[str] = _q(D_FEST),
              phase: Optional[str] = _q(D_PHASE), cpcb_class: Optional[str] = _q(D_CLASS),
              top: Optional[str] = _q("Number of ghats to list (default 3)."),
              lang: Optional[str] = _q("en, hi or both (default both).")):
        q = _query(request, {"year", "festival", "phase", "cpcb_class", "top", "lang"})
        ds = store.get()
        f = parse_filters(q, ds.catalog, ("year", "festival", "phase"))
        cls = parse_cpcb_class(q.get("cpcb_class"), available_classes(ds.criteria))
        top_n = parse_int(q.get("top"), "top", 3, 1, len(ds.catalog.sites))
        lg = (q.get("lang") or "both").strip().lower()
        if lg not in ("en", "hi", "both"):
            raise FilterError("lang", f"lang must be en, hi or both; got {lg!r}.", ["en", "hi", "both"])
        data = build_brief(ds, f, cls, top_n)
        if lg != "both":
            data.pop("hi" if lg == "en" else "en")
        return {"data": data, "meta": meta(ds, f, cls)}

    frontend = resolve_frontend_dir()
    if (frontend / "index.html").is_file():
        # Mounted last so every /api route takes priority.
        app.mount("/", StaticFiles(directory=str(frontend), html=True), name="frontend")

    return app


app = create_app()
