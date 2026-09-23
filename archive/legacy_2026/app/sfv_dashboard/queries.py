"""SQL-агрегаторы для дашборда. Все запросы — к sfv.catering_items.

Контракт: каждая функция принимает Filters, возвращает list[dict] (или dict для KPI).
ВАЖНО:
  • clickhouse-driver использует %(name)s для подстановки → формат-строки CH
    нужно экранировать удвоением знака процента (`'%%Y-%%m'`).
  • CH 24.10+ анализатор ругается на `sum(sold) AS sold` (alias = имя источника).
    Поэтому во внутренних CTE поля называем сокращённо (sl/so/rv/rt),
    а внешние имена остаются содержательными (loaded/sold/revenue/...).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .core.clickhouse import query, query_one

TABLE = "sfv.catering_items"


# ─────────── фильтры ───────────
@dataclass
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    flight_out: int | None = None
    item_category: str | None = None
    item_sku: str | None = None
    min_loadings_pair: int = 10  # min n для рейс×SKU heatmap

    def where(self) -> tuple[str, dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if self.date_from:
            clauses.append("shipment_date >= %(date_from)s")
            params["date_from"] = self.date_from
        if self.date_to:
            clauses.append("shipment_date <= %(date_to)s")
            params["date_to"] = self.date_to
        if self.flight_out is not None:
            clauses.append("flight_out = %(flight_out)s")
            params["flight_out"] = self.flight_out
        if self.item_category:
            clauses.append("item_category = %(item_category)s")
            params["item_category"] = self.item_category
        if self.item_sku:
            clauses.append("item_sku = %(item_sku)s")
            params["item_sku"] = self.item_sku
        if not clauses:
            return "1=1", params
        return " AND ".join(clauses), params


# ─────────── lookups ───────────
def lookups() -> dict[str, Any]:
    flights = query(f"""
        SELECT toInt32(flight_out) AS flight_out, count() AS n
        FROM {TABLE} WHERE flight_out IS NOT NULL
        GROUP BY flight_out ORDER BY flight_out
    """)
    cats = query(f"""
        SELECT item_category, count() AS n FROM {TABLE}
        WHERE item_category != ''
        GROUP BY item_category ORDER BY n DESC
    """)
    skus = query(f"""
        SELECT item_sku, any(item_name) AS item_name, count() AS n
        FROM {TABLE} WHERE item_sku != ''
        GROUP BY item_sku ORDER BY n DESC
    """)
    rng = query_one(f"""
        SELECT min(shipment_date) AS dmin, max(shipment_date) AS dmax FROM {TABLE}
    """)
    return {"flights": flights, "categories": cats, "skus": skus, "date_range": rng}


# ─────────── KPI ───────────
def kpi(f: Filters) -> dict[str, Any]:
    """KPI на item-уровне (учитывает любые фильтры по SKU/категории корректно)."""
    where, p = f.where()
    sql = f"""
        WITH agg AS (
            SELECT
                countDistinct(shipment_id)                                AS n_ships,
                sum(loaded_qty)                                           AS sum_loaded,
                sum(sold_qty)                                             AS sum_sold,
                sum(returned_qty)                                         AS sum_returned,
                sum(revenue)                                              AS sum_revenue,
                countDistinct(flight_out)                                 AS n_flights,
                countDistinctIf(item_sku, item_sku != '')                 AS n_sku,
                min(shipment_date)                                        AS d_min,
                max(shipment_date)                                        AS d_max,
                countDistinct(shipment_date)                              AS d_present
            FROM {TABLE}
            WHERE {where}
        )
        SELECT
            n_ships                                       AS shipments,
            sum_loaded                                    AS loaded,
            sum_sold                                      AS sold,
            sum_returned                                  AS returned,
            sum_revenue                                   AS revenue,
            sum_sold / nullIf(sum_loaded, 0)              AS sell_through,
            sum_returned / nullIf(sum_loaded, 0)          AS return_rate,
            sum_revenue / nullIf(n_ships, 0)              AS avg_rev_per_ship,
            sum_revenue / nullIf(sum_sold, 0)             AS avg_check_per_unit,
            n_flights                                     AS uniq_flights,
            n_sku                                         AS uniq_sku,
            d_min                                         AS dmin,
            d_max                                         AS dmax,
            d_present                                     AS days_present
        FROM agg
    """
    return query_one(sql, p) or {}


# ─────────── динамика по неделям ───────────
def weekly(f: Filters) -> list[dict[str, Any]]:
    where, p = f.where()
    sql = f"""
        SELECT
            toMonday(shipment_date)                                AS week_start,
            countDistinct(shipment_id)                             AS shipments,
            sum(loaded_qty)                                        AS loaded,
            sum(sold_qty)                                          AS sold,
            sum(returned_qty)                                      AS returned,
            sum(revenue)                                           AS revenue,
            sum(sold_qty) / nullIf(sum(loaded_qty), 0)             AS sell_through,
            sum(returned_qty) / nullIf(sum(loaded_qty), 0)         AS return_rate
        FROM {TABLE}
        WHERE {where}
        GROUP BY week_start ORDER BY week_start
    """
    return query(sql, p)


# ─────────── heatmap month × dow ───────────
DOW_NAMES = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}


def heatmap_month_dow(f: Filters) -> dict[str, Any]:
    """Среднее по выручке/накладной (а не сумма!) — учитывает фильтры по item-уровню."""
    where, p = f.where()
    sql = f"""
        WITH per_ship AS (
            SELECT shipment_id,
                   formatDateTime(any(shipment_date), '%%Y-%%m') AS ym,
                   toDayOfWeek(any(shipment_date))               AS dow,
                   sum(revenue)                                  AS ship_rev
            FROM {TABLE}
            WHERE {where}
            GROUP BY shipment_id
        )
        SELECT ym, dow,
               count()       AS n,
               avg(ship_rev) AS avg_rev,
               sum(ship_rev) AS sum_rev
        FROM per_ship
        GROUP BY ym, dow ORDER BY ym, dow
    """
    rows = query(sql, p)
    months = sorted({r["ym"] for r in rows})
    dows = [1, 2, 3, 4, 5, 6, 7]
    by = {(r["ym"], r["dow"]): r for r in rows}
    z_rev: list[list[float | None]] = []
    z_n: list[list[int | None]] = []
    for m in months:
        row_r, row_n = [], []
        for d in dows:
            cell = by.get((m, d))
            row_r.append(float(cell["avg_rev"]) if cell and cell["avg_rev"] is not None else None)
            row_n.append(int(cell["n"]) if cell else 0)
        z_rev.append(row_r)
        z_n.append(row_n)
    return {
        "y": months,
        "x": [DOW_NAMES[d] for d in dows],
        "z_avg_revenue": z_rev,
        "z_shipments": z_n,
    }


# ─────────── Pareto SKU ───────────
def sku_pareto(f: Filters, top: int = 30) -> list[dict[str, Any]]:
    where, p = f.where()
    p["top"] = top
    sql = f"""
        WITH agg AS (
            SELECT item_sku,
                   any(item_name)             AS name_,
                   any(item_category)         AS cat_,
                   sum(revenue)               AS rev_,
                   sum(sold_qty)              AS sold_,
                   sum(loaded_qty)            AS loaded_,
                   countDistinct(shipment_id) AS loadings_
            FROM {TABLE}
            WHERE item_sku != '' AND {where}
            GROUP BY item_sku
        ),
        with_total AS (
            SELECT *, sum(rev_) OVER () AS total_rev
            FROM agg
        )
        SELECT item_sku,
               name_     AS item_name,
               cat_      AS item_category,
               rev_      AS revenue,
               sold_     AS sold,
               loaded_   AS loaded,
               loadings_ AS loadings,
               rev_ / nullIf(total_rev, 0) AS share
        FROM with_total
        ORDER BY rev_ DESC
        LIMIT %(top)s
    """
    rows = query(sql, p)
    cum = 0.0
    for r in rows:
        cum += float(r["share"] or 0)
        r["cum_share"] = cum
    return rows


# ─────────── SKU full table ───────────
def sku_table(f: Filters) -> list[dict[str, Any]]:
    where, p = f.where()
    sql = f"""
        SELECT
            item_sku,
            any(item_name)                                          AS name_,
            any(item_category)                                      AS cat_,
            countDistinct(shipment_id)                              AS loadings,
            sum(loaded_qty)                                         AS loaded_total,
            sum(sold_qty)                                           AS sold_total,
            sum(returned_qty)                                       AS returned_total,
            sum(revenue)                                            AS rev_,
            avg(loaded_qty)                                         AS avg_loaded,
            avg(sold_qty)                                           AS avg_sold,
            sum(sold_qty) / nullIf(sum(loaded_qty), 0)              AS sell_through,
            quantile(0.5)(return_pct)                               AS med_return_pct,
            avg(price)                                              AS avg_price,
            countIf(loaded_qty > 0 AND sold_qty >= loaded_qty)
                / nullIf(countIf(loaded_qty > 0), 0)                AS soldout_share
        FROM {TABLE}
        WHERE item_sku != '' AND {where}
        GROUP BY item_sku
        ORDER BY rev_ DESC
    """
    rows = query(sql, p)
    for r in rows:
        r["item_name"] = r.pop("name_")
        r["item_category"] = r.pop("cat_")
        r["revenue"] = r.pop("rev_")
    return rows


# ─────────── категории ───────────
def categories(f: Filters) -> list[dict[str, Any]]:
    where, p = f.where()
    sql = f"""
        SELECT
            item_category,
            sum(revenue)                                            AS revenue,
            sum(loaded_qty)                                         AS loaded,
            sum(sold_qty)                                           AS sold,
            sum(returned_qty)                                       AS returned,
            sum(sold_qty) / nullIf(sum(loaded_qty), 0)              AS sell_through,
            100 * sum(returned_qty) / nullIf(sum(loaded_qty), 0)    AS return_pct
        FROM {TABLE}
        WHERE {where}
        GROUP BY item_category
        ORDER BY revenue DESC
    """
    return query(sql, p)


# ─────────── категория × месяц ───────────
def heatmap_category_month(f: Filters) -> dict[str, Any]:
    where, p = f.where()
    sql = f"""
        SELECT
            item_category,
            formatDateTime(shipment_date, '%%Y-%%m') AS ym,
            sum(revenue) AS revenue
        FROM {TABLE}
        WHERE {where}
        GROUP BY item_category, ym
        ORDER BY ym
    """
    rows = query(sql, p)
    cats = sorted({r["item_category"] for r in rows})
    months = sorted({r["ym"] for r in rows})
    by = {(r["item_category"], r["ym"]): float(r["revenue"] or 0) for r in rows}
    z = [[by.get((c, m), 0.0) for m in months] for c in cats]
    return {"y": cats, "x": months, "z": z}


# ─────────── рейсы ───────────
def flights_summary(f: Filters) -> list[dict[str, Any]]:
    where, p = f.where()
    sql = f"""
        WITH per_ship AS (
            SELECT shipment_id,
                   any(flight_out) AS fo,
                   sum(loaded_qty) AS sl,
                   sum(sold_qty)   AS so,
                   sum(revenue)    AS rv,
                   sum(returned_qty) AS rt
            FROM {TABLE}
            WHERE flight_out IS NOT NULL AND {where}
            GROUP BY shipment_id
        ),
        per_flight AS (
            SELECT
                fo                                          AS flight_out,
                count()                                     AS n,
                avg(sl)                                     AS avg_loaded,
                avg(so)                                     AS avg_sold,
                avg(rv)                                     AS avg_revenue,
                sum(so) / nullIf(sum(sl), 0)                AS sell_through,
                100 * sum(rt) / nullIf(sum(sl), 0)          AS avg_return,
                sum(rv)                                     AS total_revenue
            FROM per_ship GROUP BY fo
        ),
        stats AS (
            SELECT avg(sell_through) AS m, stddevPop(sell_through) AS s
            FROM per_flight WHERE n >= 20
        )
        SELECT pf.*,
               (pf.sell_through - s.m) / nullIf(s.s, 0) AS z_st
        FROM per_flight pf, stats s
        ORDER BY total_revenue DESC
    """
    return query(sql, p)


# ─────────── heatmap рейс × SKU ───────────
def flight_sku_heatmap(f: Filters, top_flights: int = 15, top_skus: int = 15) -> dict[str, Any]:
    where, p = f.where()
    p.update({"min_n": f.min_loadings_pair, "tf": top_flights, "ts": top_skus})
    sql = f"""
        WITH base AS (
            SELECT toInt32(flight_out) AS flight_out, item_sku,
                   any(item_name)             AS name_,
                   any(item_category)         AS cat_,
                   countDistinct(shipment_id) AS pair_n,
                   sum(loaded_qty)            AS loaded,
                   sum(sold_qty)              AS sold,
                   sum(revenue)               AS revenue,
                   sum(sold_qty) / nullIf(sum(loaded_qty), 0) AS sell_through
            FROM {TABLE}
            WHERE flight_out IS NOT NULL AND item_sku != '' AND {where}
            GROUP BY flight_out, item_sku
        ),
        flt AS (SELECT * FROM base WHERE pair_n >= %(min_n)s),
        top_f AS (
            SELECT flight_out, sum(revenue) AS rev FROM flt
            GROUP BY flight_out ORDER BY rev DESC LIMIT %(tf)s
        ),
        top_s AS (
            SELECT item_sku, sum(revenue) AS rev FROM flt
            GROUP BY item_sku ORDER BY rev DESC LIMIT %(ts)s
        )
        SELECT flight_out, item_sku,
               name_ AS item_name, cat_ AS item_category,
               pair_n, loaded, sold, revenue, sell_through
        FROM flt
        WHERE flight_out IN (SELECT flight_out FROM top_f)
          AND item_sku   IN (SELECT item_sku   FROM top_s)
    """
    rows = query(sql, p)
    flights_set = sorted({r["flight_out"] for r in rows})
    skus_set = sorted({r["item_sku"] for r in rows})
    by_rev = {(r["flight_out"], r["item_sku"]): r for r in rows}
    z_rev, z_st, z_n = [], [], []
    for fl in flights_set:
        rr, sr, nr = [], [], []
        for sk in skus_set:
            cell = by_rev.get((fl, sk))
            rr.append(float(cell["revenue"]) if cell and cell["revenue"] is not None else None)
            sr.append(float(cell["sell_through"]) if cell and cell["sell_through"] is not None else None)
            nr.append(int(cell["pair_n"]) if cell else 0)
        z_rev.append(rr); z_st.append(sr); z_n.append(nr)
    return {
        "y": [str(fl) for fl in flights_set],
        "x": skus_set,
        "z_revenue": z_rev,
        "z_sell_through": z_st,
        "z_n": z_n,
    }


# ─────────── паттерны ───────────
def dow_pattern(f: Filters) -> list[dict[str, Any]]:
    where, p = f.where()
    sql = f"""
        WITH per_ship AS (
            SELECT shipment_id,
                   toDayOfWeek(any(shipment_date)) AS dow,
                   sum(loaded_qty) AS sl,
                   sum(sold_qty)   AS so,
                   sum(revenue)    AS rv,
                   sum(returned_qty) AS rt
            FROM {TABLE}
            WHERE {where}
            GROUP BY shipment_id
        )
        SELECT dow, count() AS n,
               avg(sl) AS avg_loaded,
               avg(so) AS avg_sold,
               avg(rv) AS avg_revenue,
               100 * sum(rt) / nullIf(sum(sl), 0) AS avg_return
        FROM per_ship GROUP BY dow ORDER BY dow
    """
    rows = query(sql, p)
    for r in rows:
        r["dow_name"] = DOW_NAMES.get(int(r["dow"]), str(r["dow"]))
    return rows


def monthly(f: Filters) -> list[dict[str, Any]]:
    where, p = f.where()
    sql = f"""
        WITH per_ship AS (
            SELECT shipment_id,
                   formatDateTime(any(shipment_date), '%%Y-%%m') AS ym,
                   sum(loaded_qty) AS sl,
                   sum(sold_qty)   AS so,
                   sum(revenue)    AS rv,
                   sum(returned_qty) AS rt
            FROM {TABLE}
            WHERE {where}
            GROUP BY shipment_id
        )
        SELECT ym AS month, count() AS n,
               avg(rv)                                       AS avg_revenue,
               100 * sum(rt) / nullIf(sum(sl), 0)            AS avg_return,
               sum(rv)                                       AS total_revenue,
               sum(so) / nullIf(sum(sl), 0)                  AS sell_through
        FROM per_ship GROUP BY ym ORDER BY ym
    """
    return query(sql, p)


def sku_lifecycle(f: Filters) -> list[dict[str, Any]]:
    where, p = f.where()
    sql = f"""
        SELECT item_sku,
               any(item_name)             AS name_,
               any(item_category)         AS cat_,
               min(shipment_date)         AS first_seen,
               max(shipment_date)         AS last_seen,
               countDistinct(shipment_id) AS loadings,
               sum(revenue)               AS rev_
        FROM {TABLE}
        WHERE item_sku != '' AND {where}
        GROUP BY item_sku
        ORDER BY first_seen
    """
    rows = query(sql, p)
    for r in rows:
        r["item_name"] = r.pop("name_")
        r["item_category"] = r.pop("cat_")
        r["revenue"] = r.pop("rev_")
    return rows


def gaps(f: Filters) -> list[dict[str, Any]]:
    where, p = f.where()
    sql = f"""
        WITH days AS (
            SELECT arrayJoin(
                arrayMap(i -> toDate(d_min + i),
                         range(toUInt32(d_max - d_min) + 1))
            ) AS day
            FROM (
                SELECT min(shipment_date) AS d_min, max(shipment_date) AS d_max
                FROM {TABLE} WHERE {where}
            )
        ),
        present AS (SELECT DISTINCT shipment_date AS day FROM {TABLE} WHERE {where})
        SELECT day FROM days
        WHERE day NOT IN (SELECT day FROM present)
        ORDER BY day
    """
    missing = [r["day"] for r in query(sql, p)]
    if not missing:
        return []
    groups: list[dict[str, Any]] = []
    start = prev = missing[0]
    for d in missing[1:]:
        if (d - prev).days == 1:
            prev = d
            continue
        groups.append({"start": start.isoformat(), "end": prev.isoformat(), "days": (prev - start).days + 1})
        start = prev = d
    groups.append({"start": start.isoformat(), "end": prev.isoformat(), "days": (prev - start).days + 1})
    return groups


def return_outlier_weeks(f: Filters, threshold_z: float = 1.5) -> list[dict[str, Any]]:
    where, p = f.where()
    p["thr"] = threshold_z
    sql = f"""
        WITH per_ship AS (
            SELECT shipment_id, toMonday(any(shipment_date)) AS week,
                   sum(loaded_qty)   AS sl,
                   sum(returned_qty) AS rt,
                   sum(revenue)      AS rv
            FROM {TABLE} WHERE {where}
            GROUP BY shipment_id
        ),
        per_week AS (
            SELECT week, count() AS n,
                   sum(rt) / nullIf(sum(sl), 0) AS return_rate,
                   sum(rv) AS revenue
            FROM per_ship GROUP BY week
        ),
        st AS (SELECT avg(return_rate) AS m, stddevPop(return_rate) AS s FROM per_week)
        SELECT week, n, return_rate, revenue,
               (return_rate - st.m) / nullIf(st.s, 0) AS z
        FROM per_week, st
        WHERE abs((return_rate - st.m) / nullIf(st.s, 0)) >= %(thr)s
        ORDER BY week
    """
    return query(sql, p)
