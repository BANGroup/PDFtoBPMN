"""ClickHouse client wrapper для SFV-дашборда.

clickhouse-driver.Client НЕ потокобезопасен на уровне одного соединения.
FastAPI sync-эндпоинты исполняются в thread-pool (anyio), поэтому каждому
потоку выдаём свой Client через threading.local. Это дешевле, чем создавать
коннекшн на запрос, и безопаснее общего синглтона.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from clickhouse_driver import Client
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT / ".env"

load_dotenv(ENV_PATH, override=False)

_TLS = threading.local()


def _new_client() -> Client:
    host = os.environ["CLICKHOUSE_HOST"]
    port = int(os.environ.get("CLICKHOUSE_PORT", 9000))
    user = os.environ["CLICKHOUSE_USER"]
    pwd = os.environ["CLICKHOUSE_PASSWORD"]
    db = os.environ.get("CLICKHOUSE_DATABASE", "default")
    return Client(
        host=host,
        port=port,
        user=user,
        password=pwd,
        database=db,
        connect_timeout=10,
        send_receive_timeout=60,
        settings={
            "max_execution_time": 30,
            "use_numpy": False,
            # Старый анализатор: терпимо относится к alias=column_name,
            # которое местами невозможно избежать в наших агрегатах.
            "enable_analyzer": 0,
            "allow_experimental_analyzer": 0,
        },
    )


def get_client() -> Client:
    cli: Client | None = getattr(_TLS, "client", None)
    if cli is None:
        cli = _new_client()
        _TLS.client = cli
    return cli


def _exec(sql: str, params: dict[str, Any] | None, with_columns: bool):
    """Безопасный execute: при сетевых ошибках пересоздаёт клиент и пробует ещё раз."""
    try:
        cli = get_client()
        return cli.execute(sql, params or {}, with_column_types=with_columns)
    except (OSError, EOFError, ConnectionError) as e:
        # соединение оборвалось — пересоздаём для этого потока
        try:
            old = getattr(_TLS, "client", None)
            if old is not None:
                old.disconnect()
        except Exception:
            pass
        _TLS.client = _new_client()
        return _TLS.client.execute(sql, params or {}, with_column_types=with_columns)


def query(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows, cols = _exec(sql, params, with_columns=True)
    keys = [c[0] for c in cols]
    return [dict(zip(keys, row)) for row in rows]


def query_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def query_scalar(sql: str, params: dict[str, Any] | None = None) -> Any:
    rows, _ = _exec(sql, params, with_columns=False)
    return rows[0][0] if rows else None
