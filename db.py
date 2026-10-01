"""Base de datos SQLite: conexión, tablas y migraciones."""
import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "tecnocar.db")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS clientes(
    id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, empresa TEXT,
    telefono TEXT NOT NULL, email TEXT);
CREATE TABLE IF NOT EXISTS vehiculos(
    id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    descripcion TEXT NOT NULL, patente TEXT);
CREATE TABLE IF NOT EXISTS turnos(
    id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    vehiculo_id INTEGER NOT NULL REFERENCES vehiculos(id),
    servicio TEXT NOT NULL, fecha TEXT NOT NULL, hora TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente', comentarios TEXT,
    creado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS historial(
    id INTEGER PRIMARY KEY, vehiculo_id INTEGER NOT NULL REFERENCES vehiculos(id),
    fecha TEXT NOT NULL, km INTEGER, tipo TEXT NOT NULL, detalle TEXT, monto REAL,
    creado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS presupuestos(
    id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    vehiculo_id INTEGER REFERENCES vehiculos(id), fecha TEXT NOT NULL,
    validez_dias INTEGER NOT NULL DEFAULT 15, items TEXT NOT NULL, notas TEXT,
    total REAL NOT NULL DEFAULT 0, creado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""
# Columnas agregadas después: se suman a bases ya existentes sin perder datos.
COLUMNAS_NUEVAS = {
    "clientes": [("cuil_cuit", "TEXT"), ("notas", "TEXT")],
    "vehiculos": [("marca", "TEXT"), ("modelo", "TEXT"), ("anio", "INTEGER"),
                  ("km", "INTEGER"), ("notas", "TEXT")],
}
INDICES = """
CREATE INDEX IF NOT EXISTS ix_turnos_franja ON turnos(fecha, hora);
CREATE INDEX IF NOT EXISTS ix_vehiculos_patente ON vehiculos(patente);
CREATE INDEX IF NOT EXISTS ix_clientes_cuil ON clientes(cuil_cuit);
CREATE INDEX IF NOT EXISTS ix_historial_vehiculo ON historial(vehiculo_id, fecha);
CREATE INDEX IF NOT EXISTS ix_presupuestos_cliente ON presupuestos(cliente_id);
"""


def conn():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_db():
    with conn() as c:
        c.executescript(ESQUEMA)
        for tabla, columnas in COLUMNAS_NUEVAS.items():
            existentes = {r["name"] for r in c.execute(f"PRAGMA table_info({tabla})")}
            for nombre, tipo in columnas:
                if nombre not in existentes:
                    c.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}")
        c.executescript(INDICES)
