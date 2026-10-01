"""Servicios, marcas y modelos del formulario. Editá esta lista para agregar más."""
SERVICIOS = [
    "Mecánica general",
    "Service y mantenimiento",
    "Diagnóstico electrónico",
    "Chapa y pintura",
    "Neumáticos y alineación",
    "Aire acondicionado",
    "Equipos de GNC",
    "Flotas y logística",
]

_GRUPOS = [
    ("Producción nacional (ADEFA)", {
        "Toyota": ["Etios", "Yaris", "Corolla", "Corolla Cross", "RAV4", "Hilux", "SW4"],
        "Volkswagen": ["Gol", "Polo", "Virtus", "Nivus", "T-Cross", "Taos", "Vento", "Tiguan",
                       "Saveiro", "Amarok", "Transporter"],
        "Ford": ["Ranger", "Maverick", "Territory", "Focus", "Fiesta", "EcoSport", "Kuga", "Transit"],
        "Fiat": ["Argo", "Cronos", "Mobi", "Pulse", "Fastback", "Toro", "Strada", "Fiorino", "Ducato"],
        "Peugeot": ["208", "2008", "308", "408", "Partner", "Expert", "Boxer"],
        "Citroën": ["C3", "C4 Cactus", "C3 Aircross", "Berlingo", "Jumper"],
        "Renault": ["Kwid", "Sandero", "Stepway", "Logan", "Duster", "Oroch", "Kangoo", "Master", "Alaskan"],
        "Nissan": ["March", "Versa", "Sentra", "Kicks", "Frontier"],
        "Chevrolet": ["Onix", "Onix Plus", "Cruze", "Tracker", "S10", "Spin", "Montana", "Equinox"],
        "Mercedes-Benz": ["Sprinter", "Vito", "Clase A", "Clase C", "Clase E", "GLA", "GLC"],
    }),
    ("Otras marcas", {
        "Honda": ["Civic", "City", "Fit", "HR-V", "CR-V"],
        "Hyundai": ["HB20", "Creta", "Tucson", "Santa Fe", "H1"],
        "Kia": ["Rio", "Cerato", "Seltos", "Sportage", "Sorento"],
        "Jeep": ["Renegade", "Compass", "Commander"],
        "RAM": ["Rampage", "1500", "2500", "ProMaster"],
        "BYD": ["Dolphin", "Dolphin Mini", "Song Plus", "Yuan Plus", "Seal", "King"],
        "Chery": ["Tiggo 2", "Tiggo 3", "Tiggo 4 Pro", "Tiggo 7 Pro", "Tiggo 8 Pro"],
    }),
    ("Más marcas", {
        "BAIC": ["X25", "X35", "X55", "BJ40", "U5 Plus"],
        "Haval / GWM": ["H6", "Jolion", "Dargo", "Poer"],
        "Changan": ["CS15", "CS35 Plus", "CS55 Plus", "Hunter", "UNI-T"],
        "JAC": ["JS2", "JS3", "JS4", "T6", "T8"],
        "Jetour": ["X70", "X70 Plus", "X90 Plus", "Dashing"],
        "MG": ["ZS", "HS", "MG3", "MG5"],
        "DFSK": ["500", "580", "C31", "C35"],
        "Foton": ["Tunland", "Aumark", "View", "Toano"],
        "Shineray": ["T30", "X30", "X30L"],
        "Geely": ["Coolray", "Emgrand", "Azkarra", "Geometry C"],
        "Leapmotor": ["T03", "C10", "B10"],
        "Lynk & Co": ["01", "05", "06"],
    }),
    ("Alta gama", {
        "Audi": ["A1", "A3", "A4", "A5", "Q2", "Q3", "Q5", "Q7"],
        "BMW": ["Serie 1", "Serie 3", "Serie 5", "X1", "X3", "X5"],
        "Volvo": ["XC40", "XC60", "XC90", "S60", "C40"],
        "DS Automobiles": ["DS 3", "DS 4", "DS 7"],
        "Alfa Romeo": ["Giulia", "Stelvio", "Tonale", "Giulietta"],
        "Porsche": ["911", "Cayenne", "Macan", "Panamera", "Taycan"],
        "Lexus": ["UX", "NX", "RX", "ES"],
        "Mini": ["Cooper", "Countryman", "Clubman"],
        "Land Rover": ["Defender", "Discovery", "Discovery Sport", "Range Rover", "Evoque", "Velar"],
        "Jaguar": ["XE", "F-Pace", "E-Pace", "I-Pace", "F-Type"],
    }),
]
GRUPOS = [{"grupo": g, "marcas": list(m)} for g, m in _GRUPOS]
# Cada marca lleva sus modelos ordenados y la opción "Otro modelo".
CATALOGO = {marca: sorted(mods) + ["Otro modelo"] for _, m in _GRUPOS for marca, mods in m.items()}
