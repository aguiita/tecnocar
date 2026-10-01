"""Tecnocar - gestor de turnos (FastAPI + SQLite).
Ejecutar:  uvicorn main:app --reload
"""
import os
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

import validaciones as val
from admin_api import router as admin_router
from catalogo import CATALOGO, GRUPOS, SERVICIOS
from db import conn, init_db

BASE = os.path.dirname(__file__)

# ---- Configuración de turnos (se cambia acá) ----
CUPO = 2                                # autos por horario: al llegar a 2 reservas, el horario queda no disponible
MANANA = (9, 14)                        # 9 a 14 h  -> turnos 9, 10, 11, 12 y 13
TARDE = (15, 20)                        # 15 a 20 h -> turnos 15, 16, 17, 18 y 19 (lunes a viernes)
VENTANA_DESDE = date(2026, 10, 1)       # primer día en que se puede sacar turno
VENTANA_HASTA = date(2026, 12, 31)      # último día en que se puede sacar turno
ESTADOS = ["pendiente", "confirmado", "en_taller", "listo", "cancelado"]


def rango() -> tuple[date, date]:
    return max(date.today(), VENTANA_DESDE), VENTANA_HASTA


def horarios(d: date) -> list[str]:
    """Lunes a viernes 9-13 y 15-19; sábados 9-13; domingo cerrado. Turnos de 1 hora."""
    if d.weekday() == 6:
        return []
    horas = list(range(*MANANA)) + ([] if d.weekday() == 5 else list(range(*TARDE)))
    if d == date.today():
        horas = [h for h in horas if h > datetime.now().hour]
    return [f"{h:02d}:00" for h in horas]


init_db()
app = FastAPI(title="Tecnocar")


@app.exception_handler(RequestValidationError)
async def errores_de_validacion(request, exc):
    e = exc.errors()[0]
    if e["type"] == "value_error":
        msg = str(e["msg"]).replace("Value error, ", "")
    else:
        campo = ".".join(str(x) for x in e["loc"][1:]) or "formulario"
        msg = f"Revisá el campo «{campo}»."
    return JSONResponse(status_code=422, content={"detail": msg})


class TurnoIn(BaseModel):
    nombre: str
    empresa: Optional[str] = Field(default=None, max_length=80)
    telefono: str
    email: Optional[str] = Field(default=None, max_length=120)
    marca: str
    modelo: str
    patente: str
    servicio: str
    fecha: date
    hora: str
    comentarios: Optional[str] = Field(default=None, max_length=500)

    @field_validator("nombre", "empresa", "telefono", "email", "marca", "modelo",
                     "servicio", "hora", "comentarios", mode="before")
    @classmethod
    def _limpiar(cls, v):
        return val.limpiar(v)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v):
        return val.nombre(v)

    @field_validator("telefono")
    @classmethod
    def _telefono(cls, v):
        return val.telefono(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return val.email(v)

    @field_validator("patente", mode="before")
    @classmethod
    def _patente(cls, v):
        return val.patente(v)

    @model_validator(mode="after")
    def _resto(self):
        if self.marca not in CATALOGO:
            raise ValueError("Elegí una marca de la lista.")
        if self.modelo not in CATALOGO[self.marca]:
            raise ValueError("Elegí un modelo de la lista para esa marca.")
        if self.servicio not in SERVICIOS:
            raise ValueError("Elegí un servicio de la lista.")
        if self.fecha < date.today():
            raise ValueError("La fecha ya pasó.")
        if self.fecha < VENTANA_DESDE:
            raise ValueError("Los turnos se habilitan desde el 1 de octubre de 2026.")
        if self.fecha > VENTANA_HASTA:
            raise ValueError("Por ahora solo se toman turnos hasta el 31 de diciembre de 2026.")
        if self.fecha.weekday() == 6:
            raise ValueError("Los domingos no atendemos.")
        if self.hora not in horarios(self.fecha):
            raise ValueError("Elegí un horario válido para ese día.")
        return self


def ocupacion(c, d: date) -> dict:
    return {r["hora"]: r["n"] for r in c.execute(
        "SELECT hora, COUNT(*) n FROM turnos WHERE fecha=? AND estado!='cancelado' GROUP BY hora",
        (d.isoformat(),))}


@app.get("/api/servicios")
def api_servicios():
    return SERVICIOS


@app.get("/api/marcas")
def api_marcas():
    return GRUPOS


@app.get("/api/modelos")
def api_modelos(marca: str):
    if marca not in CATALOGO:
        raise HTTPException(404, "Marca no encontrada")
    return CATALOGO[marca]


@app.get("/api/config")
def api_config():
    desde, hasta = rango()
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat()}


@app.get("/api/disponibilidad")
def api_disponibilidad(fecha: date):
    """Todas las franjas del día; libres=0 significa que ya está reservada."""
    desde, hasta = rango()
    if not desde <= fecha <= hasta:
        return []
    with conn() as c:
        usados = ocupacion(c, fecha)
    return [{"hora": h, "libres": max(0, CUPO - usados.get(h, 0))} for h in horarios(fecha)]


@app.get("/api/calendario")
def api_calendario(mes: str):
    """Días reservables del mes (AAAA-MM) con la cantidad de franjas libres."""
    try:
        anio, m = (int(x) for x in mes.split("-"))
        primero = date(anio, m, 1)
    except ValueError:
        raise HTTPException(400, "Mes inválido. Usá el formato AAAA-MM.")
    siguiente = date(anio + (m == 12), m % 12 + 1, 1)
    desde, hasta = rango()
    with conn() as c:
        filas = c.execute(
            "SELECT fecha, hora, COUNT(*) n FROM turnos WHERE fecha>=? AND fecha<? "
            "AND estado!='cancelado' GROUP BY fecha, hora",
            (primero.isoformat(), siguiente.isoformat())).fetchall()
    usados = {(f["fecha"], f["hora"]): f["n"] for f in filas}
    dias, d = [], primero
    while d < siguiente:
        if desde <= d <= hasta:
            hs = horarios(d)
            libres = sum(1 for h in hs if usados.get((d.isoformat(), h), 0) < CUPO)
            dias.append({"fecha": d.isoformat(), "libres": libres, "total": len(hs)})
        d += timedelta(days=1)
    return dias


@app.post("/api/turnos", status_code=201)
def crear_turno(t: TurnoIn):
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")  # evita que dos personas tomen el mismo horario
        if ocupacion(c, t.fecha).get(t.hora, 0) >= CUPO:
            raise HTTPException(409, "Ese horario ya fue reservado. Elegí otro.")
        veh = c.execute("SELECT id, cliente_id FROM vehiculos WHERE patente=? ORDER BY id LIMIT 1",
                        (t.patente,)).fetchone()
        if veh:  # auto ya conocido: se usa su cliente, sin duplicar datos
            dup = c.execute("""SELECT 1 FROM turnos x JOIN vehiculos v ON v.id=x.vehiculo_id
                               WHERE x.fecha=? AND v.patente=? AND x.estado!='cancelado'""",
                            (t.fecha.isoformat(), t.patente)).fetchone()
            if dup:
                raise HTTPException(409, "Ya hay un turno para esa patente en esa fecha.")
            cli, vid = veh["cliente_id"], veh["id"]
        else:
            fila = c.execute("SELECT id FROM clientes WHERE telefono=? AND lower(nombre)=lower(?) LIMIT 1",
                             (t.telefono, t.nombre)).fetchone()
            cli = fila["id"] if fila else c.execute(
                "INSERT INTO clientes(nombre,empresa,telefono,email) VALUES(?,?,?,?)",
                (t.nombre, t.empresa, t.telefono, t.email)).lastrowid
            vid = c.execute("INSERT INTO vehiculos(cliente_id,descripcion,marca,modelo,patente) VALUES(?,?,?,?,?)",
                            (cli, f"{t.marca} {t.modelo}", t.marca, t.modelo, t.patente)).lastrowid
        tid = c.execute(
            "INSERT INTO turnos(cliente_id,vehiculo_id,servicio,fecha,hora,comentarios) VALUES(?,?,?,?,?,?)",
            (cli, vid, t.servicio, t.fecha.isoformat(), t.hora, t.comentarios)).lastrowid
        c.commit()
        return {"id": tid, "fecha": t.fecha, "hora": t.hora}
    except HTTPException:
        c.rollback()
        raise
    finally:
        c.close()


app.include_router(admin_router)


@app.get("/admin")
def admin():
    return FileResponse(os.path.join(BASE, "static", "admin.html"))


app.mount("/", StaticFiles(directory=os.path.join(BASE, "static"), html=True), name="static")
