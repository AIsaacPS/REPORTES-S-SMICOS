"""
Análisis de desempeño SkyAlert
Uso: python3 analisis_desempeno.py sismos/YYYY-MM-DD_HHMMSS/
"""

import csv, os, sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyArrowPatch
from scipy.stats import gaussian_kde
from math import radians, sin, cos, sqrt, atan2
import importlib.util

# ── Configuración del evento ───────────────────────────────────────────────────
if len(sys.argv) < 2:
    print("Uso: python3 analisis_desempeno.py sismos/<YYYY-MM-DD_HHMMSS>/")
    sys.exit(1)

_sismo_dir = os.path.abspath(sys.argv[1])
_cfg_path = os.path.join(_sismo_dir, "config.py")
_spec = importlib.util.spec_from_file_location("config", _cfg_path)
_cfg  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cfg)

CSV_PATH = _cfg.CSV_ENCUESTA
OUT_DIR  = _cfg.OUT_DIR
EPI_LAT  = _cfg.EPICENTRO[1]
EPI_LON  = _cfg.EPICENTRO[0]

FELT_ORDER  = ["didnt-feel", "weak", "moderate", "strong", "violent"]
FELT_LABELS = ["No sintió", "Débil", "Moderado", "Fuerte", "Violento"]
FELT_COLORS = ["#757575", "#87CEEB", "#FF8C00", "#E53935", "#B71C1C"]

ACC_ORDER   = ["correct", "dont-know", "weaker", "stronger"]
ACC_LABELS  = ["Correcta", "No sabe", "Más débil", "Más fuerte"]
ACC_COLORS  = ["#66BB6A", "#78909C", "#42A5F5", "#EF5350"]

EA_ORDER    = ["audible-alert", "silent-notification", "dont-know", "not-necessary"]
EA_LABELS   = ["Sí, con una alerta audible", "Sí, con una notificación silenciosa", "No lo sé", "No era necesario avisarme"]
EA_COLORS   = ["#FFD600", "#8D6E63", "#78909C", "#EF5350"]

DIST_EDGES  = [0, 50, 150, 300, 600]
DIST_LABELS = ["0–50 km", "50–150 km", "150–300 km", ">300 km"]

BG    = "#1A1A2E"
PANEL = "#16213E"
GRID  = "#2A2A4A"
TEXT  = "#E0E0E0"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat, dlon = radians(lat2-lat1), radians(lon2-lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

# ── Carga ──────────────────────────────────────────────────────────────────────
rows = []
with open(CSV_PATH, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        try:
            lat = float(r["coordinates[1]"])
            lon = float(r["coordinates[0]"])
        except ValueError:
            continue
        rows.append({
            "felt":     r.get("howIFelt", "didnt-feel"),
            "accuracy": r.get("accuracy", "dont-know"),
            "expect":   r.get("expectAlert", ""),
            "dist":     haversine(EPI_LAT, EPI_LON, lat, lon),
            "min":      int(r["createdAt"][11:13]) * 60 + int(r["createdAt"][14:16]),
        })

total = len(rows)

def dist_bin(d):
    for i in range(len(DIST_EDGES)-1):
        if d < DIST_EDGES[i+1]:
            return i
    return len(DIST_EDGES)-2

# ── Figura ─────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 10,
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT, "ytick.color": TEXT,
})

fig = plt.figure(figsize=(16, 10), facecolor=BG)
fig.suptitle(
    f"Evaluación del Sistema de Alerta Temprana  ·  SkyAlert\n"
    f"M{_cfg.MAGNITUD}  |  {_cfg.DESCRIPCION}  |  {_cfg.HORA_CONFIRMACION}  "
    f"(Latencia de confirmación Lc: {_cfg.LC} s)",
    fontsize=14, fontweight="bold", color=TEXT, y=0.98
)

gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.35,
                       left=0.07, right=0.96, top=0.91, bottom=0.07)

def style_ax(ax, title):
    ax.set_facecolor(PANEL)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID)
    ax.tick_params(colors=TEXT, labelsize=9)
    ax.set_title(title, color=TEXT, fontsize=11, fontweight="bold", pad=10)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6, linestyle="--")
    ax.set_axisbelow(True)

# ══════════════════════════════════════════════════════════════════════════════
# Subplot 1 — Donut: howIFelt
# ══════════════════════════════════════════════════════════════════════════════
ax1 = fig.add_subplot(gs[0, 0])
ax1.set_facecolor(PANEL)
ax1.set_aspect("equal")
ax1.axis("off")
ax1.set_title("Percepción del sismo", color=TEXT, fontsize=11, fontweight="bold", pad=10)

counts_felt = [sum(1 for r in rows if r["felt"] == k) for k in FELT_ORDER]
non_zero = [(c, l, col) for c, l, col in zip(counts_felt, FELT_LABELS, FELT_COLORS) if c > 0]
sizes, labels_f, colors_f = zip(*non_zero)

wedges, _ = ax1.pie(
    sizes, colors=colors_f, startangle=90,
    wedgeprops={"width": 0.45, "edgecolor": BG, "linewidth": 2},
    radius=1.0
)

# Centro del donut
ax1.text(0, 0, f"n = {total:,}", ha="center", va="center",
         fontsize=11, fontweight="bold", color=TEXT)

# Leyenda lateral limpia
legend_patches = [
    plt.Rectangle((0,0),1,1, fc=col, ec="none")
    for col in colors_f
]
legend_labels = [f"{l}  {c/total*100:.1f}%  ({c:,})"
                 for l, c in zip(labels_f, sizes)]
ax1.legend(legend_patches, legend_labels, loc="lower center",
           bbox_to_anchor=(0.5, -0.22), ncol=2, fontsize=8,
           frameon=False, labelcolor=TEXT, handlelength=1.2, handleheight=1.2)

# ══════════════════════════════════════════════════════════════════════════════
# Subplot 2 — Donut: expectAlert
# ══════════════════════════════════════════════════════════════════════════════
ax2 = fig.add_subplot(gs[0, 1])
ax2.set_facecolor(PANEL)
ax2.set_aspect("equal")
ax2.axis("off")
ax2.set_title("¿Consideras que debimos alertarte?", color=TEXT, fontsize=11, fontweight="bold", pad=10)

counts_ea = [sum(1 for r in rows if r["expect"] == k) for k in EA_ORDER]
non_zero2 = [(c, l, col) for c, l, col in zip(counts_ea, EA_LABELS, EA_COLORS) if c > 0]
sizes2, labels_a, colors_a = zip(*non_zero2)
total_ea = sum(sizes2)

ax2.pie(
    sizes2, colors=colors_a, startangle=90,
    wedgeprops={"width": 0.45, "edgecolor": BG, "linewidth": 2},
    radius=1.0
)
ax2.text(0, 0, f"n = {total_ea:,}", ha="center", va="center",
         fontsize=11, fontweight="bold", color=TEXT)

legend_patches2 = [plt.Rectangle((0,0),1,1, fc=col, ec="none") for col in colors_a]
legend_labels2  = [f"{l}  {c/total_ea*100:.1f}%  ({c:,})"
                   for l, c in zip(labels_a, sizes2)]
ax2.legend(legend_patches2, legend_labels2, loc="lower center",
           bbox_to_anchor=(0.5, -0.22), ncol=2, fontsize=8,
           frameon=False, labelcolor=TEXT, handlelength=1.2, handleheight=1.2)

# ══════════════════════════════════════════════════════════════════════════════
# Subplot 3 — Barras apiladas: percepción por zona de alertamiento
# ══════════════════════════════════════════════════════════════════════════════
import json as _json
from math import radians as _rad, sin as _sin, cos as _cos, sqrt as _sqrt, atan2 as _atan2

_CONFIRMING_CLUSTER = _cfg.CLUSTER_CONFIRMADOR
_CONFIRMING_GALS    = _cfg.GALS_CONFIRMACION
_INTENSITY_SCALE    = [("Débil",1,5),("Leve",5.01,21),("Moderado",21.01,35),
                       ("Fuerte",35.01,77),("Violento",77.01,156),("Severo",156.01,9999)]
_INTENSITY_COLORS   = ["#87CEEB","#66BB6A","#FFD600","#FF8C00","#E53935","#B71C1C"]

def _oidx(gals):
    for i,(_, lo, hi) in enumerate(_INTENSITY_SCALE):
        if lo <= gals <= hi: return i
    return 0

_clusters = {}
with open(_cfg.CSV_RADIOS, encoding="utf-8") as _f:
    for _row in csv.DictReader(_f):
        _loc = _json.loads(_row["Location"])
        _clusters[_row["Name"]] = {
            "lon": _loc["coordinates"][0], "lat": _loc["coordinates"][1],
            "grid": _json.loads(_row["Grid Distances"])
        }

_cl      = _clusters[_CONFIRMING_CLUSTER]
_clat, _clon = _cl["lat"], _cl["lon"]
_oi      = _oidx(_CONFIRMING_GALS)
_radii   = _cl["grid"][_oi]
_zones   = [(_r, _INTENSITY_SCALE[_oi-i][0], _INTENSITY_COLORS[_oi-i])
            for i, _r in enumerate(_radii) if 0 <= _oi-i < len(_INTENSITY_SCALE)]

_zone_labels = [l for _, l, _ in _zones] + [f"> {_zones[-1][0]} km"]
_zone_radii  = [r for r, _, _ in _zones]

def _get_zone(d):
    for i, r in enumerate(_zone_radii):
        if d <= r: return i
    return len(_zone_radii)

def _hav(lat1, lon1, lat2, lon2):
    R = 6371
    dlat, dlon = _rad(lat2-lat1), _rad(lon2-lon1)
    a = _sin(dlat/2)**2 + _cos(_rad(lat1))*_cos(_rad(lat2))*_sin(dlon/2)**2
    return R * 2 * _atan2(_sqrt(a), _sqrt(1-a))

_users_by_zone = [[] for _ in _zone_labels]
for r in rows:
    # recalcular distancia desde el cluster confirmador
    _d = _hav(_clat, _clon,
               float(r.get("lat", 0)) if "lat" in r else 0,
               float(r.get("lon", 0)) if "lon" in r else 0)
    _users_by_zone[_get_zone(_d)].append(r["felt"])

# Re-leer coordenadas del CSV para distancia al cluster
_users_by_zone = [[] for _ in _zone_labels]
with open(CSV_PATH, encoding="utf-8") as _f:
    for _row in csv.DictReader(_f):
        try:
            _lat = float(_row["coordinates[1]"])
            _lon = float(_row["coordinates[0]"])
        except ValueError:
            continue
        _users_by_zone[_get_zone(_hav(_clat, _clon, _lat, _lon))].append(
            _row.get("howIFelt", "didnt-feel")
        )

FELT_KEYS_Z  = ["didnt-feel", "weak", "moderate", "strong", "violent"]
FELT_COLS_Z  = ["#757575", "#87CEEB", "#FF8C00", "#E53935", "#B71C1C"]
FELT_LABS_Z  = ["No sintió", "Débil", "Moderado", "Fuerte", "Violento"]

ax3 = fig.add_subplot(gs[1, 0])
style_ax(ax3, f"Percepción por zona de alertamiento\n({_CONFIRMING_CLUSTER} | {_INTENSITY_SCALE[_oi][0]}, {_CONFIRMING_GALS} gals)")
ax3.yaxis.grid(True, color=GRID, linewidth=0.6, linestyle="--")

_x, _bot = np.arange(len(_zone_labels)), np.zeros(len(_zone_labels))
for key, color, label in zip(FELT_KEYS_Z, FELT_COLS_Z, FELT_LABS_Z):
    _vals = np.array([z.count(key) for z in _users_by_zone], dtype=float)
    _tots = np.array([len(z) for z in _users_by_zone], dtype=float)
    _pcts = np.where(_tots > 0, _vals / _tots * 100, 0)
    ax3.bar(_x, _pcts, bottom=_bot, width=0.65, color=color,
            label=label, edgecolor=BG, linewidth=0.6)
    for i, (p, b) in enumerate(zip(_pcts, _bot)):
        if p > 7:
            ax3.text(i, b + p/2, f"{p:.0f}%", ha="center", va="center",
                     fontsize=8, color="white", fontweight="bold")
    _bot += _pcts

ax3.axvline(len(_zone_radii) - 0.5, color="#FFD600", linewidth=1.2,
            linestyle="--", label="Límite zona alerta")
ax3.set_xticks(_x)
ax3.set_xticklabels(
    [f"{l}\n(n={len(z):,})" for l, z in zip(_zone_labels, _users_by_zone)],
    fontsize=8.5
)
ax3.set_ylabel("% de respuestas", color=TEXT)
ax3.set_ylim(0, 108)
ax3.legend(loc="center left", fontsize=8, frameon=True,
           facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT,
           ncol=1, bbox_to_anchor=(1.02, 0.5))

# ══════════════════════════════════════════════════════════════════════════════
# Subplot 4 — KDE: distribución temporal de respuestas
# ══════════════════════════════════════════════════════════════════════════════
ax4 = fig.add_subplot(gs[1, 1])
style_ax(ax4, "Distribución temporal de respuestas")

minutes = np.array([r["min"] for r in rows], dtype=float)
kde = gaussian_kde(minutes, bw_method=0.08)
x_min, x_max = minutes.min() - 10, minutes.max() + 10
x_kde = np.linspace(x_min, x_max, 500)
y_kde = kde(x_kde) * total  # escalar a conteo

ax4.fill_between(x_kde, y_kde, alpha=0.25, color="#42A5F5")
ax4.plot(x_kde, y_kde, color="#42A5F5", linewidth=2)

# Línea del sismo (15:19 UTC)
sismo_min = 15 * 60 + 19
ax4.axvline(sismo_min, color="#EF5350", linewidth=1.5, linestyle="--", label="Hora del sismo (UTC)")

# Eje X en formato HH:MM
tick_mins = np.arange(int(x_min // 60) * 60, int(x_max // 60 + 1) * 60 + 1, 60)
ax4.set_xticks(tick_mins)
ax4.set_xticklabels([f"{int(m//60):02d}:00" for m in tick_mins], fontsize=8)
ax4.set_xlabel("Hora (UTC)", color=TEXT)
ax4.set_ylabel("Densidad de respuestas", color=TEXT)
ax4.legend(fontsize=8, frameon=False, labelcolor=TEXT)

plt.savefig(os.path.join(OUT_DIR, "evaluacion_desempeno.png"), dpi=180, facecolor=BG)
plt.close()
print("✅ evaluacion_desempeno.png generado")
