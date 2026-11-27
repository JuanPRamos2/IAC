"""Acceso a PostgreSQL. Las consultas siempre van parametrizadas."""
import contextlib
import os

import psycopg2
import psycopg2.extras
from psycopg2 import pool

_pool = None


def _dsn():
    return (f"host={os.environ.get('PG_HOST','datos')} "
            f"port={os.environ.get('PG_PUERTO','5432')} "
            f"dbname={os.environ.get('PG_BASE','bienestar')} "
            f"user={os.environ.get('PG_USUARIO','bienestar_app')} "
            f"password={os.environ.get('PG_CLAVE','')} "
            f"application_name={os.environ.get('NOMBRE_SERVICIO','microservicio')}")


def _statement_timeout_ms() -> int:
    try:
        return max(0, int(os.environ.get("PG_STATEMENT_TIMEOUT_MS", "5000")))
    except ValueError:
        return 5000


def obtener_pool():
    global _pool
    if _pool is None:
        timeout_ms = _statement_timeout_ms()
        kwargs = {}
        if timeout_ms > 0:
            kwargs["options"] = f"-c statement_timeout={timeout_ms}"
        _pool = pool.ThreadedConnectionPool(
            1, int(os.environ.get("PG_POOL_MAX", "5")), _dsn(), **kwargs
        )
    return _pool


@contextlib.contextmanager
def cursor(commit: bool = False):
    p = obtener_pool()
    cn = p.getconn()
    try:
        with cn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        cn.commit() if commit else cn.rollback()
    except Exception:
        cn.rollback()
        raise
    finally:
        p.putconn(cn)


def consultar(sql, params=None):
    with cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def consultar_uno(sql, params=None):
    with cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def ping():
    with cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()
