"""FastAPI сервер дашборда. Запуск:

    uvicorn app.sfv_dashboard.server:app --host 0.0.0.0 --port 8765 --workers 2

Все эндпоинты под /api/* отдают JSON. Корень / отдаёт SPA (static/index.html).
Фильтры передаются как query-параметры: date_from, date_to, flight_out, item_category, item_sku.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from . import queries as q
from .core.clickhouse import get_client

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="SFV Catering Dashboard", version="2.0.0")


def _filters(date_from: date | None, date_to: date | None,
             flight_out: int | None, item_category: str | None,
             item_sku: str | None, min_n: int = 10) -> q.Filters:
    return q.Filters(
        date_from=date_from, date_to=date_to,
        flight_out=flight_out, item_category=item_category,
        item_sku=item_sku, min_loadings_pair=min_n,
    )


def _normalize(obj: Any) -> Any:
    """Decimal/Date/Datetime → primitive, рекурсивно."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    return obj


def jr(payload: Any) -> JSONResponse:
    return JSONResponse(content=_normalize(jsonable_encoder(payload)))


@app.get("/api/health")
def health():
    cli = get_client()
    ver = cli.execute("SELECT version()")[0][0]
    cnt = cli.execute(f"SELECT count() FROM {q.TABLE}")[0][0]
    return jr({"status": "ok", "ch_version": ver, "table": q.TABLE, "rows": cnt})


@app.get("/api/lookups")
def get_lookups():
    return jr(q.lookups())


@app.get("/api/kpi")
def get_kpi(date_from: date | None = None, date_to: date | None = None,
            flight_out: int | None = None, item_category: str | None = None,
            item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.kpi(f))


@app.get("/api/weekly")
def get_weekly(date_from: date | None = None, date_to: date | None = None,
               flight_out: int | None = None, item_category: str | None = None,
               item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.weekly(f))


@app.get("/api/heatmap/month-dow")
def get_heatmap_month_dow(date_from: date | None = None, date_to: date | None = None,
                          flight_out: int | None = None, item_category: str | None = None,
                          item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.heatmap_month_dow(f))


@app.get("/api/sku/pareto")
def get_sku_pareto(top: int = Query(30, ge=5, le=200),
                   date_from: date | None = None, date_to: date | None = None,
                   flight_out: int | None = None, item_category: str | None = None,
                   item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.sku_pareto(f, top=top))


@app.get("/api/sku/table")
def get_sku_table(date_from: date | None = None, date_to: date | None = None,
                  flight_out: int | None = None, item_category: str | None = None,
                  item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.sku_table(f))


@app.get("/api/categories")
def get_categories(date_from: date | None = None, date_to: date | None = None,
                   flight_out: int | None = None, item_category: str | None = None,
                   item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.categories(f))


@app.get("/api/heatmap/category-month")
def get_heatmap_cat_month(date_from: date | None = None, date_to: date | None = None,
                          flight_out: int | None = None, item_category: str | None = None,
                          item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.heatmap_category_month(f))


@app.get("/api/flights/summary")
def get_flights(date_from: date | None = None, date_to: date | None = None,
                flight_out: int | None = None, item_category: str | None = None,
                item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.flights_summary(f))


@app.get("/api/flights/heatmap")
def get_flight_sku_heat(top_flights: int = Query(15, ge=5, le=40),
                        top_skus: int = Query(15, ge=5, le=40),
                        min_n: int = Query(10, ge=1, le=200),
                        date_from: date | None = None, date_to: date | None = None,
                        flight_out: int | None = None, item_category: str | None = None,
                        item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku, min_n=min_n)
    return jr(q.flight_sku_heatmap(f, top_flights=top_flights, top_skus=top_skus))


@app.get("/api/dow")
def get_dow(date_from: date | None = None, date_to: date | None = None,
            flight_out: int | None = None, item_category: str | None = None,
            item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.dow_pattern(f))


@app.get("/api/monthly")
def get_monthly(date_from: date | None = None, date_to: date | None = None,
                flight_out: int | None = None, item_category: str | None = None,
                item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.monthly(f))


@app.get("/api/sku/lifecycle")
def get_lifecycle(date_from: date | None = None, date_to: date | None = None,
                  flight_out: int | None = None, item_category: str | None = None,
                  item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.sku_lifecycle(f))


@app.get("/api/gaps")
def get_gaps(date_from: date | None = None, date_to: date | None = None,
             flight_out: int | None = None, item_category: str | None = None,
             item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.gaps(f))


@app.get("/api/return-outliers")
def get_return_outliers(threshold_z: float = Query(1.5, ge=0.5, le=5.0),
                        date_from: date | None = None, date_to: date | None = None,
                        flight_out: int | None = None, item_category: str | None = None,
                        item_sku: str | None = None):
    f = _filters(date_from, date_to, flight_out, item_category, item_sku)
    return jr(q.return_outlier_weeks(f, threshold_z=threshold_z))


# ─────────── статика ───────────
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
