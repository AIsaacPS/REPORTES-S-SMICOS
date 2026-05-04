"""
parse_reporte.py — Extrae parámetros del reporte de REDSkyAlert (TXT o HTML)
y genera config.py + copia la encuesta en la carpeta del sismo.

Uso:
    python3 parse_reporte.py <ruta_reporte_txt_o_html> <ruta_csv_encuesta>

Ejemplo:
    python3 parse_reporte.py reporte_preliminar.txt encuesta-04-05-2026.csv
"""

import re, os, sys, shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS   = os.path.join(BASE_DIR, "assets")
SISMOS   = os.path.join(BASE_DIR, "sismos")

# ── Parser TXT ─────────────────────────────────────────────────────────────────
def parse_txt(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()

    # Magnitud y ubicación desde título/resumen
    m = re.search(r"M([\d.]+)\s*\|\s*(.+?)(?:\n|$)", text)
    if not m:
        m = re.search(r"M([\d.]+)\s+(.+?)(?:\n|$)", text)
    magnitud = float(m.group(1))
    descripcion = m.group(2).strip().rstrip(" |")

    # Epicentro: lat/lon
    coord = re.search(r"([\d.]+)°\s*N\s*/\s*(-?[\d.]+)°\s*[OW]", text)
    lat_epi = float(coord.group(1))
    lon_epi = float(coord.group(2))
    if lon_epi > 0:
        lon_epi = -lon_epi

    # Profundidad
    prof = re.search(r"(\d+)\s*km\s*de\s*profundidad", text)
    profundidad = float(prof.group(1)) if prof else 0.0

    # Fecha/hora SSN (UTC)
    fecha_utc = re.search(r"(\d{1,2}:\d{2}:\d{2})\s*UTC\)", text)
    if not fecha_utc:
        fecha_utc = re.search(r"(\d{1,2}:\d{2}:\d{2})\s*UTC", text)
    hora_utc = fecha_utc.group(1)

    # Fecha del sismo
    fecha = re.search(r"(\d{1,2})[/\s](?:de\s)?(\w+)[/\s](?:de\s)?(\d{4})", text)
    meses = {"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05",
             "junio":"06","julio":"07","agosto":"08","septiembre":"09",
             "octubre":"10","noviembre":"11","diciembre":"12"}
    dia = fecha.group(1).zfill(2)
    mes = meses.get(fecha.group(2).lower(), fecha.group(2).zfill(2))
    anio = fecha.group(3)
    fecha_ssn_str = f"{dia}/{mes}/{anio} - {hora_utc}.000"

    # Cluster confirmador y gales — de la tabla "Primer registro"
    conf = re.search(
        r"(?:Sensor de confirmación|Cuajinicuilapa|Primer registro)\s*\n?"
        r"\s*(\S.*?)\s*\n\s*(\d+)\s*\n\s*([\d.]+)\s*\n\s*(\d{1,2}:\d{2}:\d{2})\s*UTC",
        text
    )
    if not conf:
        # Fallback: buscar en tabla con formato "Cluster \t sensor \t Lc \t hora"
        conf = re.search(
            r"Sensor de confirmación\s*\n\s*(.+?)\s*\n\s*(\d+)\s*\n\s*([\d.]+)",
            text
        )
    cluster_confirmador = conf.group(1).strip() if conf else "Desconocido"
    gals_line = re.search(r"Cuajinicuilapa.*?([\d.]+)", text, re.DOTALL)

    # Gales de confirmación — buscar en tabla de clústeres activos
    gals_confirmacion = 0.0
    if cluster_confirmador != "Desconocido":
        gals_match = re.search(
            rf"{re.escape(cluster_confirmador)}\s+[\d.]+\s+([\d.]+)",
            text
        )
        if gals_match:
            gals_confirmacion = float(gals_match.group(1))

    # Lc
    lc_match = re.search(r"(?:Lc|[Ll]atencia.*?confirmación.*?)\s*(?:de\s+)?([\d.]+)\s*s", text)
    lc = float(lc_match.group(1)) if lc_match else 0.0

    # Hora de confirmación
    hora_conf_match = re.search(r"(\d{1,2}:\d{2}:\d{2})\s*UTC\s*$", text, re.MULTILINE)
    if hora_conf_match:
        hora_conf_str = f"{dia}/{mes}/{anio} - {hora_conf_match.group(1)}.000"
    else:
        # Calcular desde hora SSN + Lc
        parts = hora_utc.split(":")
        total_s = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2]) + lc + 1
        h, rem = divmod(int(total_s), 3600)
        mi, s = divmod(rem, 60)
        hora_conf_str = f"{dia}/{mes}/{anio} - {h:02d}:{mi:02d}:{s:02d}.000"

    dt_conf = datetime.strptime(hora_conf_str, "%d/%m/%Y - %H:%M:%S.%f")
    folder_id = dt_conf.strftime("%Y-%m-%d_%H%M%S")

    return {
        "folder_id": folder_id,
        "epicentro": descripcion,
        "magnitud": magnitud,
        "profundidad": profundidad,
        "lat_epi": lat_epi,
        "lon_epi": lon_epi,
        "fecha_ssn": fecha_ssn_str,
        "hora_confirmacion": hora_conf_str,
        "cluster_confirmador": cluster_confirmador,
        "gals_confirmacion": gals_confirmacion,
        "lc": lc,
    }

# ── Parser HTML (legacy) ──────────────────────────────────────────────────────
def parse_html(path):
    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text, self.skip = [], False
        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"): self.skip = True
        def handle_endtag(self, tag):
            if tag in ("script", "style"): self.skip = False
        def handle_data(self, data):
            if not self.skip:
                s = data.strip()
                if s: self.text.append(s)

    with open(path, encoding="utf-8") as f:
        html = f.read()
    p = TextExtractor()
    p.feed(html)
    text = "\n".join(p.text)

    ssn = re.search(
        r"Magnitud\nProfundidad\nLatitud\nLongitud\n"
        r"(\d{2}/\d{2}/\d{4} - \d{2}:\d{2}:\d{2}\.\d+)\n"
        r"(.+?)\n([\d.]+)\n([\d.]+)\n([\d.]+)\n(-[\d.]+)", text)
    if not ssn:
        raise ValueError("No se encontró el bloque SSN en el HTML")

    fecha_ssn_str = ssn.group(1)
    epicentro = ssn.group(2)
    magnitud = float(ssn.group(3))
    profundidad = float(ssn.group(4))
    lat_epi = float(ssn.group(5))
    lon_epi = float(ssn.group(6))

    titulo = re.search(r"Reporte del sismo ocurrido el (\d{2}/\d{2}/\d{4} - \d{2}:\d{2}:\d{2}\.\d+)", text)
    hora_confirmacion = titulo.group(1) if titulo else fecha_ssn_str

    primer = re.search(
        r"Primer registro\n(.+?)\n([\d.]+)\nSensor: (\d+)\nFecha: (\d{2}/\d{2}/\d{4} - \d{2}:\d{2}:\d{2}\.\d+)", text)
    if not primer:
        raise ValueError("No se encontró 'Primer registro' en el HTML")

    cluster_confirmador = primer.group(1).strip()
    gals_confirmacion = float(primer.group(2))

    def to_sec(s):
        dt = datetime.strptime(s, "%d/%m/%Y - %H:%M:%S.%f")
        return dt.hour*3600 + dt.minute*60 + dt.second + dt.microsecond/1e6

    lc = round(to_sec(hora_confirmacion) - to_sec(fecha_ssn_str) - 1.0, 1)
    dt_conf = datetime.strptime(hora_confirmacion, "%d/%m/%Y - %H:%M:%S.%f")
    folder_id = dt_conf.strftime("%Y-%m-%d_%H%M%S")

    return {
        "folder_id": folder_id, "epicentro": epicentro,
        "magnitud": magnitud, "profundidad": profundidad,
        "lat_epi": lat_epi, "lon_epi": lon_epi,
        "fecha_ssn": fecha_ssn_str, "hora_confirmacion": hora_confirmacion,
        "cluster_confirmador": cluster_confirmador,
        "gals_confirmacion": gals_confirmacion, "lc": lc,
    }

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python3 parse_reporte.py <reporte.txt|.html> <encuesta.csv>")
        sys.exit(1)

    reporte_path = os.path.abspath(sys.argv[1])
    csv_path = os.path.abspath(sys.argv[2])

    # Detectar formato
    ext = os.path.splitext(reporte_path)[1].lower()
    if ext == ".txt":
        params = parse_txt(reporte_path)
    else:
        params = parse_html(reporte_path)

    # Crear carpeta del sismo
    sismo_dir = os.path.join(SISMOS, params["folder_id"])
    out_dir = os.path.join(sismo_dir, "output")
    os.makedirs(out_dir, exist_ok=True)

    # Copiar inputs al sismo
    reporte_dest = os.path.join(sismo_dir, "reporte" + ext)
    if os.path.abspath(reporte_path) != os.path.abspath(reporte_dest):
        shutil.copy2(reporte_path, reporte_dest)

    encuesta_dest = os.path.join(sismo_dir, "encuesta.csv")
    if os.path.abspath(csv_path) != os.path.abspath(encuesta_dest):
        shutil.copy2(csv_path, encuesta_dest)

    # Generar config.py
    config_path = os.path.join(sismo_dir, "config.py")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(f'# Auto-generado por parse_reporte.py\n')
        f.write(f'import os\n')
        f.write(f'_BASE = os.path.dirname(os.path.abspath(__file__))\n')
        f.write(f'_ROOT = os.path.dirname(os.path.dirname(_BASE))\n\n')
        f.write(f'REPORTE        = os.path.join(_BASE, "reporte{ext}")\n')
        f.write(f'CSV_ENCUESTA   = os.path.join(_BASE, "encuesta.csv")\n')
        f.write(f'CSV_RADIOS     = os.path.join(_ROOT, "assets", "RadiosDeAlertamiento.csv")\n')
        f.write(f'CSV_RED        = os.path.join(_ROOT, "assets", "REDSkyAlert_2026.csv")\n')
        f.write(f'SENSOR_ICON    = os.path.join(_ROOT, "assets", "MX.png")\n')
        f.write(f'SHAPE_ESTADOS  = os.path.join(_ROOT, "assets", "Division_estatal", "dest23cw.shp")\n')
        f.write(f'OUT_DIR        = os.path.join(_BASE, "output")\n\n')
        f.write(f'EPICENTRO          = ({params["lon_epi"]}, {params["lat_epi"]})\n')
        f.write(f'MAGNITUD           = {params["magnitud"]}\n')
        f.write(f'PROFUNDIDAD        = {params["profundidad"]}\n')
        f.write(f'DESCRIPCION        = {repr(params["epicentro"])}\n')
        f.write(f'FECHA_SSN          = {repr(params["fecha_ssn"])}\n')
        f.write(f'HORA_CONFIRMACION  = {repr(params["hora_confirmacion"])}\n')
        f.write(f'LC                 = {params["lc"]}  # Latencia de confirmación (s)\n')
        f.write(f'CLUSTER_CONFIRMADOR = {repr(params["cluster_confirmador"])}\n')
        f.write(f'GALS_CONFIRMACION  = {params["gals_confirmacion"]}\n')

    print(f"✅ config.py generado en: {config_path}")
    print(f"   Carpeta del sismo: {sismo_dir}")
    for k, v in params.items():
        print(f"   {k}: {v}")
