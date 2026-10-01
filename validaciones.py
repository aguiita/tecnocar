"""Validaciones compartidas por el formulario público y el panel de administración."""
import re

LETRAS = "A-Za-zÁÉÍÓÚÜÑáéíóúüñ"
RE_NOMBRE = re.compile(rf"^[{LETRAS}][{LETRAS} .'\-]{{1,79}}$")
RE_TEL = re.compile(r"^\+?[\d ()\-]{8,20}$")
RE_MAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
# Patente anterior: ABC123  |  Mercosur: AB123CD
RE_PATENTE = re.compile(r"^([A-Z]{3}\d{3}|[A-Z]{2}\d{3}[A-Z]{2})$")


def limpiar(v):
    """Recorta espacios; un texto vacío pasa a None."""
    return (v.strip() or None) if isinstance(v, str) else v


def nombre(v):
    if v is not None and not RE_NOMBRE.match(v):
        raise ValueError("El nombre solo puede tener letras y espacios.")
    return v


def telefono(v):
    if v is not None and (not RE_TEL.match(v) or not 8 <= len(re.sub(r"\D", "", v)) <= 15):
        raise ValueError("Teléfono inválido. Usá solo números, por ejemplo 11 2345-6789.")
    return v


def email(v):
    if v and not RE_MAIL.match(v):
        raise ValueError("El email no es válido.")
    return v


def patente(v):
    v = re.sub(r"[\s\-]", "", str(v)).upper()
    if not RE_PATENTE.match(v):
        raise ValueError("Patente inválida. Formatos aceptados: ABC123 o AB123CD.")
    return v


def cuil_cuit(v):
    """Acepta con o sin guiones; guarda solo los 11 dígitos. Verifica el dígito verificador."""
    if v is None:
        return None
    d = re.sub(r"\D", "", v)
    if len(d) != 11:
        raise ValueError("El CUIL/CUIT debe tener 11 números.")
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    dv = 11 - sum(int(a) * b for a, b in zip(d[:10], pesos)) % 11
    dv = 0 if dv == 11 else dv
    if dv == 10 or dv != int(d[10]):
        raise ValueError("El CUIL/CUIT no es válido: el dígito verificador no coincide.")
    return d
