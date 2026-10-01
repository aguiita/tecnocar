"""API del panel de administración: clientes, autos, historial, presupuestos, turnos e importación."""
import csv
import io
import json
import os
import re
import unicodedata
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

import validaciones as val
from db import conn

# Clave del panel. Para publicarlo en internet, definila como variable de entorno ADMIN_KEY.
ADMIN_KEY = os.getenv("ADMIN_KEY", "triburc46")
ESTADOS = ["pendiente", "confirmado", "en_taller", "listo", "cancelado"]


def requerir_admin(x_admin_key: Optional[str] = Header(None)):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(401, "Clave incorrecta")


router = APIRouter(prefix="/api", dependencies=[Depends(requerir_admin)])


# ---------- Modelos ----------
class ClienteIn(BaseModel):
    nombre: str
    empresa: Optional[str] = Field(default=None, max_length=80)
    cuil_cuit: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = Field(default=None, max_length=120)
    notas: Optional[str] = Field(default=None, max_length=500)

    @field_validator("nombre", "empresa", "cuil_cuit", "telefono", "email", "notas", mode="before")
    @classmethod
    def _limpiar(cls, v):
        return val.limpiar(v)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v):
        return val.nombre(v)

    @field_validator("cuil_cuit")
    @classmethod
    def _cuil(cls, v):
        return val.cuil_cuit(v)

    @field_validator("telefono")
    @classmethod
    def _tel(cls, v):
        return val.telefono(v)

    @field_validator("email")
    @classmethod
    def _mail(cls, v):
        return val.email(v)


class VehiculoIn(BaseModel):
    marca: str = Field(min_length=1, max_length=40)
    modelo: str = Field(min_length=1, max_length=40)
    patente: str
    anio: Optional[int] = Field(default=None, ge=1950, le=2100)
    km: Optional[int] = Field(default=None, ge=0, le=2_000_000)
    notas: Optional[str] = Field(default=None, max_length=500)

    @field_validator("marca", "modelo", "notas", mode="before")
    @classmethod
    def _limpiar(cls, v):
        return val.limpiar(v)

    @field_validator("patente", mode="before")
    @classmethod
    def _patente(cls, v):
        return val.patente(v)


class ClienteNuevoIn(ClienteIn):
    """Alta de cliente; opcionalmente con su primer auto ya cargado y vinculado."""
    vehiculo: Optional[VehiculoIn] = None


class ServicioIn(BaseModel):
    fecha: date
    km: Optional[int] = Field(default=None, ge=0, le=2_000_000)
    tipo: str = Field(min_length=2, max_length=60)
    detalle: Optional[str] = Field(default=None, max_length=1000)
    monto: Optional[float] = Field(default=None, ge=0, le=1_000_000_000)

    @field_validator("tipo", "detalle", mode="before")
    @classmethod
    def _limpiar(cls, v):
        return val.limpiar(v)

    @field_validator("fecha")
    @classmethod
    def _fecha(cls, v):
        if v > date.today():
            raise ValueError("La fecha del arreglo no puede ser futura.")
        return v


class ItemIn(BaseModel):
    descripcion: str = Field(min_length=1, max_length=200)
    cantidad: float = Field(gt=0, le=10000)
    precio: float = Field(ge=0, le=1_000_000_000)


class PresupuestoIn(BaseModel):
    cliente_id: int
    vehiculo_id: Optional[int] = None
    validez_dias: int = Field(default=15, ge=1, le=90)
    items: list[ItemIn] = Field(min_length=1, max_length=60)
    notas: Optional[str] = Field(default=None, max_length=500)

    @field_validator("notas", mode="before")
    @classmethod
    def _limpiar(cls, v):
        return val.limpiar(v)


class EstadoIn(BaseModel):
    estado: str


class ImportIn(BaseModel):
    csv: str
    confirmar: bool = False


# ---------- Utilidades ----------
def _fila(c, tabla, id_, mensaje):
    r = c.execute(f"SELECT * FROM {tabla} WHERE id=?", (id_,)).fetchone()
    if not r:
        raise HTTPException(404, mensaje)
    return r


def _cuil_libre(c, cuil, excluir):
    if cuil:
        r = c.execute("SELECT nombre FROM clientes WHERE cuil_cuit=? AND id IS NOT ?", (cuil, excluir)).fetchone()
        if r:
            raise HTTPException(409, f"Ya existe un cliente con ese CUIL/CUIT: {r['nombre']}.")


def _patente_libre(c, patente, excluir):
    r = c.execute("""SELECT c.nombre FROM vehiculos v JOIN clientes c ON c.id=v.cliente_id
                     WHERE v.patente=? AND v.id IS NOT ?""", (patente, excluir)).fetchone()
    if r:
        raise HTTPException(409, f"Esa patente ya está cargada a nombre de {r['nombre']}.")


# ---------- Turnos ----------
@router.get("/turnos")
def listar_turnos(desde: Optional[date] = None):
    desde = desde or date.today()
    with conn() as c:
        rows = c.execute("""
            SELECT t.id, t.fecha, t.hora, t.servicio, t.estado, t.comentarios, t.cliente_id, t.vehiculo_id,
                   c.nombre, c.empresa, c.telefono, v.descripcion AS vehiculo, v.patente
            FROM turnos t JOIN clientes c ON c.id=t.cliente_id JOIN vehiculos v ON v.id=t.vehiculo_id
            WHERE t.fecha >= ? ORDER BY t.fecha, t.hora""", (desde.isoformat(),)).fetchall()
    return [dict(r) for r in rows]


@router.patch("/turnos/{tid}")
def cambiar_estado(tid: int, e: EstadoIn):
    if e.estado not in ESTADOS:
        raise HTTPException(400, "Estado inválido")
    with conn() as c:
        n = c.execute("UPDATE turnos SET estado=? WHERE id=?", (e.estado, tid)).rowcount
    if not n:
        raise HTTPException(404, "Turno no encontrado")
    return {"id": tid, "estado": e.estado}


# ---------- Clientes ----------
@router.get("/admin/clientes")
def buscar_clientes(q: str = ""):
    q = q.strip()
    sql = """SELECT c.id, c.nombre, c.empresa, c.cuil_cuit, c.telefono,
        (SELECT COUNT(*) FROM vehiculos v WHERE v.cliente_id=c.id) AS autos,
        (SELECT group_concat(v.patente, ', ') FROM vehiculos v WHERE v.cliente_id=c.id) AS patentes
        FROM clientes c"""
    par = {}
    if q:
        patente = re.sub(r"[\s-]", "", q).upper()
        par = {"q": f"%{q.lower()}%", "p": f"%{patente}%", "d": re.sub(r"\D", "", q)}
        sql += """ WHERE lower(c.nombre) LIKE :q OR lower(coalesce(c.empresa,'')) LIKE :q
            OR c.telefono LIKE :q
            OR (:d != '' AND coalesce(c.cuil_cuit,'') LIKE '%' || :d || '%')
            OR EXISTS (SELECT 1 FROM vehiculos v WHERE v.cliente_id=c.id
                       AND (upper(coalesce(v.patente,'')) LIKE :p OR lower(coalesce(v.descripcion,'')) LIKE :q))"""
    sql += " ORDER BY lower(c.nombre) LIMIT 300"
    with conn() as c:
        return [dict(r) for r in c.execute(sql, par).fetchall()]


@router.post("/admin/clientes", status_code=201)
def crear_cliente(d: ClienteNuevoIn):
    with conn() as c:
        _cuil_libre(c, d.cuil_cuit, None)
        if d.vehiculo:
            _patente_libre(c, d.vehiculo.patente, None)
        cid = c.execute("INSERT INTO clientes(nombre,empresa,cuil_cuit,telefono,email,notas) VALUES(?,?,?,?,?,?)",
                        (d.nombre, d.empresa, d.cuil_cuit, d.telefono or "", d.email, d.notas)).lastrowid
        vid = None
        if d.vehiculo:
            v = d.vehiculo
            vid = c.execute(
                "INSERT INTO vehiculos(cliente_id,descripcion,marca,modelo,patente,anio,km,notas) VALUES(?,?,?,?,?,?,?,?)",
                (cid, f"{v.marca} {v.modelo}", v.marca, v.modelo, v.patente, v.anio, v.km, v.notas)).lastrowid
    return {"id": cid, "vehiculo_id": vid}


@router.get("/admin/clientes/{cid}")
def detalle_cliente(cid: int):
    with conn() as c:
        cliente = dict(_fila(c, "clientes", cid, "Cliente no encontrado"))
        vehiculos = [dict(v) for v in c.execute("SELECT * FROM vehiculos WHERE cliente_id=? ORDER BY id", (cid,))]
        for v in vehiculos:
            v["historial"] = [dict(h) for h in c.execute(
                "SELECT * FROM historial WHERE vehiculo_id=? ORDER BY fecha DESC, id DESC", (v["id"],))]
        turnos = [dict(t) for t in c.execute(
            """SELECT t.id, t.fecha, t.hora, t.servicio, t.estado, v.descripcion AS vehiculo, v.patente
               FROM turnos t JOIN vehiculos v ON v.id=t.vehiculo_id
               WHERE t.cliente_id=? ORDER BY t.fecha DESC, t.hora DESC LIMIT 30""", (cid,))]
        presupuestos = []
        for r in c.execute("""SELECT p.*, v.descripcion AS vehiculo, v.patente FROM presupuestos p
                              LEFT JOIN vehiculos v ON v.id=p.vehiculo_id
                              WHERE p.cliente_id=? ORDER BY p.id DESC LIMIT 50""", (cid,)):
            p = dict(r)
            p["items"] = json.loads(p["items"])
            presupuestos.append(p)
    return {"cliente": cliente, "vehiculos": vehiculos, "turnos": turnos, "presupuestos": presupuestos}


@router.put("/admin/clientes/{cid}")
def modificar_cliente(cid: int, d: ClienteIn):
    with conn() as c:
        _fila(c, "clientes", cid, "Cliente no encontrado")
        _cuil_libre(c, d.cuil_cuit, cid)
        c.execute("UPDATE clientes SET nombre=?, empresa=?, cuil_cuit=?, telefono=?, email=?, notas=? WHERE id=?",
                  (d.nombre, d.empresa, d.cuil_cuit, d.telefono or "", d.email, d.notas, cid))
    return {"id": cid}


# ---------- Autos (lista y ficha) ----------
@router.get("/admin/vehiculos")
def buscar_vehiculos(q: str = ""):
    """Lista de autos con su dueño. Busca por patente, marca/modelo, dueño o empresa."""
    q = q.strip()
    sql = """SELECT v.id, v.patente, v.marca, v.modelo, v.descripcion, v.anio, v.km,
                    c.id AS cliente_id, c.nombre AS dueno, c.empresa,
                    (SELECT COUNT(*) FROM historial h WHERE h.vehiculo_id=v.id) AS arreglos,
                    (SELECT MAX(h.fecha) FROM historial h WHERE h.vehiculo_id=v.id) AS ultimo_arreglo
             FROM vehiculos v JOIN clientes c ON c.id=v.cliente_id"""
    par = {}
    if q:
        pat = re.sub(r"[\s-]", "", q).upper()
        par = {"q": f"%{q.lower()}%", "p": f"%{pat}%"}
        sql += """ WHERE upper(coalesce(v.patente,'')) LIKE :p OR lower(coalesce(v.descripcion,'')) LIKE :q
                   OR lower(c.nombre) LIKE :q OR lower(coalesce(c.empresa,'')) LIKE :q"""
    sql += " ORDER BY lower(coalesce(v.descripcion,'')), v.patente LIMIT 300"
    with conn() as c:
        return [dict(r) for r in c.execute(sql, par).fetchall()]


@router.get("/admin/vehiculos/{vid}")
def detalle_vehiculo(vid: int):
    """Ficha completa del auto: datos, dueño, historial de arreglos, turnos y presupuestos."""
    with conn() as c:
        v = dict(_fila(c, "vehiculos", vid, "Vehículo no encontrado"))
        dueno = dict(_fila(c, "clientes", v["cliente_id"], "Cliente no encontrado"))
        historial = [dict(h) for h in c.execute(
            "SELECT * FROM historial WHERE vehiculo_id=? ORDER BY fecha DESC, id DESC", (vid,))]
        turnos = [dict(t) for t in c.execute(
            """SELECT id, fecha, hora, servicio, estado, comentarios FROM turnos
               WHERE vehiculo_id=? ORDER BY fecha DESC, hora DESC LIMIT 50""", (vid,))]
        presupuestos = []
        for r in c.execute("SELECT * FROM presupuestos WHERE vehiculo_id=? ORDER BY id DESC LIMIT 50", (vid,)):
            p = dict(r)
            p["items"] = json.loads(p["items"])
            presupuestos.append(p)
    v["total_arreglos"] = round(sum(h["monto"] or 0 for h in historial), 2)
    return {"vehiculo": v, "dueno": dueno, "historial": historial,
            "turnos": turnos, "presupuestos": presupuestos}


# ---------- Vehículos e historial ----------
@router.post("/admin/clientes/{cid}/vehiculos", status_code=201)
def crear_vehiculo(cid: int, d: VehiculoIn):
    with conn() as c:
        _fila(c, "clientes", cid, "Cliente no encontrado")
        _patente_libre(c, d.patente, None)
        vid = c.execute(
            "INSERT INTO vehiculos(cliente_id,descripcion,marca,modelo,patente,anio,km,notas) VALUES(?,?,?,?,?,?,?,?)",
            (cid, f"{d.marca} {d.modelo}", d.marca, d.modelo, d.patente, d.anio, d.km, d.notas)).lastrowid
    return {"id": vid}


@router.put("/admin/vehiculos/{vid}")
def modificar_vehiculo(vid: int, d: VehiculoIn):
    with conn() as c:
        _fila(c, "vehiculos", vid, "Vehículo no encontrado")
        _patente_libre(c, d.patente, vid)
        c.execute("UPDATE vehiculos SET descripcion=?, marca=?, modelo=?, patente=?, anio=?, km=?, notas=? WHERE id=?",
                  (f"{d.marca} {d.modelo}", d.marca, d.modelo, d.patente, d.anio, d.km, d.notas, vid))
    return {"id": vid}


@router.post("/admin/vehiculos/{vid}/servicios", status_code=201)
def crear_servicio(vid: int, d: ServicioIn):
    with conn() as c:
        _fila(c, "vehiculos", vid, "Vehículo no encontrado")
        sid = c.execute("INSERT INTO historial(vehiculo_id,fecha,km,tipo,detalle,monto) VALUES(?,?,?,?,?,?)",
                        (vid, d.fecha.isoformat(), d.km, d.tipo, d.detalle, d.monto)).lastrowid
        if d.km is not None:  # el km actual del auto sube con el arreglo más reciente
            c.execute("UPDATE vehiculos SET km=? WHERE id=? AND (km IS NULL OR km<?)", (d.km, vid, d.km))
    return {"id": sid}


@router.delete("/admin/servicios/{sid}")
def borrar_servicio(sid: int):
    with conn() as c:
        if not c.execute("DELETE FROM historial WHERE id=?", (sid,)).rowcount:
            raise HTTPException(404, "Arreglo no encontrado")
    return {"id": sid}


# ---------- Presupuestos ----------
@router.post("/admin/presupuestos", status_code=201)
def crear_presupuesto(p: PresupuestoIn):
    items = [{"descripcion": i.descripcion, "cantidad": i.cantidad, "precio": i.precio} for i in p.items]
    total = round(sum(i["cantidad"] * i["precio"] for i in items), 2)
    with conn() as c:
        _fila(c, "clientes", p.cliente_id, "Cliente no encontrado")
        if p.vehiculo_id:
            v = _fila(c, "vehiculos", p.vehiculo_id, "Vehículo no encontrado")
            if v["cliente_id"] != p.cliente_id:
                raise HTTPException(400, "Ese vehículo no pertenece al cliente.")
        pid = c.execute(
            "INSERT INTO presupuestos(cliente_id,vehiculo_id,fecha,validez_dias,items,notas,total) VALUES(?,?,?,?,?,?,?)",
            (p.cliente_id, p.vehiculo_id, date.today().isoformat(), p.validez_dias,
             json.dumps(items, ensure_ascii=False), p.notas, total)).lastrowid
    return {"id": pid, "total": total}


@router.delete("/admin/presupuestos/{pid}")
def borrar_presupuesto(pid: int):
    with conn() as c:
        if not c.execute("DELETE FROM presupuestos WHERE id=?", (pid,)).rowcount:
            raise HTTPException(404, "Presupuesto no encontrado")
    return {"id": pid}


# ---------- Importar / exportar (Excel guardado como CSV) ----------
ALIAS = {
    "nombre": "nombre", "cliente": "nombre", "nombre y apellido": "nombre",
    "empresa": "empresa", "razon social": "empresa",
    "cuil": "cuil_cuit", "cuit": "cuil_cuit", "cuil cuit": "cuil_cuit", "cuil_cuit": "cuil_cuit",
    "cuil/cuit": "cuil_cuit",
    "telefono": "telefono", "tel": "telefono", "celular": "telefono", "whatsapp": "telefono",
    "email": "email", "mail": "email", "correo": "email",
    "patente": "patente", "dominio": "patente",
    "marca": "marca", "modelo": "modelo",
    "anio": "anio", "ano": "anio",
    "km": "km", "kilometros": "km", "kilometraje": "km",
    "fecha": "fecha",
    "trabajo": "tipo", "arreglo": "tipo", "tipo": "tipo", "servicio": "tipo",
    "detalle": "detalle", "descripcion": "detalle", "observaciones": "detalle",
    "monto": "monto", "importe": "monto", "precio": "monto",
}


def _norm(h):
    s = unicodedata.normalize("NFD", h.strip().lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def _entero(s):
    d = re.sub(r"\D", "", s or "")
    return int(d) if d else None


def _monto(s):
    s = (s or "").replace("$", "").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"Monto inválido: {s}")


def _fecha(s):
    for f in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s.strip(), f).date()
        except ValueError:
            pass
    raise ValueError(f"Fecha inválida: {s} (usá dd/mm/aaaa)")


def _importar(c, texto):
    texto = texto.lstrip("\ufeff")
    if not texto.strip():
        raise HTTPException(400, "El archivo está vacío.")
    primera = texto.splitlines()[0]
    delim = max((";", ",", "\t"), key=primera.count)
    lector = csv.DictReader(io.StringIO(texto), delimiter=delim)
    cols = {k: ALIAS[_norm(k)] for k in (lector.fieldnames or []) if k and _norm(k) in ALIAS}
    if "nombre" not in cols.values():
        raise HTTPException(400, "Falta la columna «nombre». Descargá la plantilla para ver el formato.")
    res = {"clientes_nuevos": 0, "clientes_existentes": 0, "autos_nuevos": 0, "arreglos_nuevos": 0,
           "repetidos": 0, "filas_con_error": 0, "errores": []}
    nuevos, existentes = set(), set()
    for n, fila in enumerate(lector, start=2):
        r = {cols[k]: (v or "").strip() for k, v in fila.items() if k in cols and isinstance(v, str)}
        if not any(r.values()):
            continue
        try:
            nombre = val.nombre(val.limpiar(r.get("nombre")))
            if not nombre:
                raise ValueError("Falta el nombre del cliente.")
            cuil = val.cuil_cuit(val.limpiar(r.get("cuil_cuit")))
            tel = val.telefono(val.limpiar(r.get("telefono")))
            mail = val.email(val.limpiar(r.get("email")))
            empresa = val.limpiar(r.get("empresa"))
            pat = val.patente(r["patente"]) if r.get("patente") else None
            marca, modelo = val.limpiar(r.get("marca")), val.limpiar(r.get("modelo"))
            anio, km = _entero(r.get("anio")), _entero(r.get("km"))
            tipo, detalle = val.limpiar(r.get("tipo")), val.limpiar(r.get("detalle"))
            monto = _monto(r.get("monto"))
            fecha = _fecha(r["fecha"]) if r.get("fecha") else None
            if anio is not None and not 1950 <= anio <= 2100:
                raise ValueError(f"Año inválido: {anio}")
            if (tipo or fecha) and not (tipo and fecha and pat):
                raise ValueError("Para cargar un arreglo hacen falta patente, fecha y trabajo.")
            if fecha and fecha > date.today():
                raise ValueError("La fecha del arreglo no puede ser futura.")
            # --- búsqueda (solo lectura) ---
            veh = c.execute("SELECT id, cliente_id FROM vehiculos WHERE patente=? ORDER BY id LIMIT 1",
                            (pat,)).fetchone() if pat else None
            cli = None
            if cuil:
                cli = c.execute("SELECT id FROM clientes WHERE cuil_cuit=?", (cuil,)).fetchone()
            if not cli and veh:
                cli = {"id": veh["cliente_id"]}
            if not cli:
                if tel:
                    cli = c.execute("SELECT id FROM clientes WHERE lower(nombre)=lower(?) AND telefono=?",
                                    (nombre, tel)).fetchone()
                else:
                    cli = c.execute("SELECT id FROM clientes WHERE lower(nombre)=lower(?) LIMIT 1",
                                    (nombre,)).fetchone()
            if pat and not veh and not (marca and modelo):
                raise ValueError(f"El auto {pat} es nuevo: faltan marca y modelo.")
        except ValueError as e:
            res["filas_con_error"] += 1
            if len(res["errores"]) < 40:
                res["errores"].append(f"Fila {n}: {e}")
            continue
        # --- escritura ---
        if cli:
            cid = cli["id"]
            existentes.add(cid)
            c.execute("""UPDATE clientes SET cuil_cuit=coalesce(cuil_cuit,?), empresa=coalesce(empresa,?),
                         email=coalesce(email,?) WHERE id=?""", (cuil, empresa, mail, cid))
        else:
            cid = c.execute("INSERT INTO clientes(nombre,empresa,cuil_cuit,telefono,email) VALUES(?,?,?,?,?)",
                            (nombre, empresa, cuil, tel or "", mail)).lastrowid
            nuevos.add(cid)
        vid = None
        if pat:
            if veh:
                vid = veh["id"]
                c.execute("UPDATE vehiculos SET marca=coalesce(marca,?), modelo=coalesce(modelo,?), anio=coalesce(anio,?) WHERE id=?",
                          (marca, modelo, anio, vid))
            else:
                vid = c.execute(
                    "INSERT INTO vehiculos(cliente_id,descripcion,marca,modelo,patente,anio,km) VALUES(?,?,?,?,?,?,?)",
                    (cid, f"{marca} {modelo}", marca, modelo, pat, anio, km)).lastrowid
                res["autos_nuevos"] += 1
        if vid and km is not None:
            c.execute("UPDATE vehiculos SET km=? WHERE id=? AND (km IS NULL OR km<?)", (km, vid, km))
        if vid and tipo:
            igual = c.execute("""SELECT 1 FROM historial WHERE vehiculo_id=? AND fecha=? AND tipo=?
                                 AND coalesce(km,-1)=coalesce(?,-1)""",
                              (vid, fecha.isoformat(), tipo, km)).fetchone()
            if igual:
                res["repetidos"] += 1
            else:
                c.execute("INSERT INTO historial(vehiculo_id,fecha,km,tipo,detalle,monto) VALUES(?,?,?,?,?,?)",
                          (vid, fecha.isoformat(), km, tipo, detalle, monto))
                res["arreglos_nuevos"] += 1
    res["clientes_nuevos"] = len(nuevos)
    res["clientes_existentes"] = len(existentes - nuevos)
    return res


@router.post("/admin/importar")
def importar(d: ImportIn):
    """Con confirmar=false solo simula (no guarda nada); con true guarda."""
    c = conn()
    try:
        c.execute("BEGIN")
        res = _importar(c, d.csv)
        res["guardado"] = bool(d.confirmar)
        c.commit() if d.confirmar else c.rollback()
        return res
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


@router.get("/admin/exportar")
def exportar():
    with conn() as c:
        rows = c.execute("""
            SELECT c.nombre, c.empresa, c.cuil_cuit, c.telefono, c.email, v.patente,
                   v.marca, v.modelo, v.descripcion, v.anio, v.km AS km_auto,
                   h.fecha, h.km AS km_arreglo, h.tipo, h.detalle, h.monto
            FROM clientes c LEFT JOIN vehiculos v ON v.cliente_id=c.id
            LEFT JOIN historial h ON h.vehiculo_id=v.id
            ORDER BY lower(c.nombre), v.id, h.fecha""").fetchall()
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["nombre", "empresa", "cuil_cuit", "telefono", "email", "patente", "marca", "modelo",
                "anio", "km", "fecha", "trabajo", "detalle", "monto"])
    for r in rows:
        marca, modelo = r["marca"], r["modelo"]
        if not marca and r["descripcion"]:
            marca, _, modelo = r["descripcion"].partition(" ")
        fecha = ""
        if r["fecha"]:
            y, m, d = r["fecha"].split("-")
            fecha = f"{d}/{m}/{y}"
        km = r["km_arreglo"] if r["fecha"] else r["km_auto"]
        w.writerow([r["nombre"], r["empresa"] or "", r["cuil_cuit"] or "", r["telefono"], r["email"] or "",
                    r["patente"] or "", marca or "", modelo or "", r["anio"] or "", "" if km is None else km,
                    fecha, r["tipo"] or "", r["detalle"] or "", "" if r["monto"] is None else r["monto"]])
    return {"csv": "\ufeff" + out.getvalue()}
