"""
Script QGIS - Mapa de evaluación SkyAlert
Ejecutar desde la consola de Python de QGIS:
    SISMO_DIR = '/ruta/a/sismos/YYYY-MM-DD_HHMMSS'
    exec(Path('/ruta/a/SKYALERT-EVALUATION/mapa_evaluacion.py').read_text())
"""

import csv, os
import numpy as np
from scipy.spatial import cKDTree
from osgeo import gdal, osr

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsField, QgsFields, QgsCoordinateReferenceSystem,
    QgsVectorFileWriter, QgsSingleSymbolRenderer, QgsCategorizedSymbolRenderer,
    QgsRendererCategory, QgsSymbol, QgsSimpleMarkerSymbolLayer,
    QgsRasterMarkerSymbolLayer, QgsRasterLayer, QgsSingleBandPseudoColorRenderer,
    QgsColorRampShader, QgsRasterShader, QgsRectangle, QgsFillSymbol
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface

# ── Configuración del evento ──────────────────────────────────────────────────
import importlib.util, sys
# SISMO_DIR debe definirse antes de exec() en la consola QGIS
if "SISMO_DIR" not in dir():
    raise RuntimeError("Define SISMO_DIR antes de ejecutar. Ej:\n"
                       "  SISMO_DIR = '/home/aisaac/Documents/SKYALERT-EVALUATION/sismos/2026-05-04_151931'")
_cfg_path = os.path.join(SISMO_DIR, "config.py")
_spec = importlib.util.spec_from_file_location("config", _cfg_path)
_cfg  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cfg)

BASE_DIR    = _cfg.OUT_DIR
CSV_PATH    = _cfg.CSV_ENCUESTA
CSV_RED     = _cfg.CSV_RED
SENSOR_ICON = _cfg.SENSOR_ICON
OUT_SURVEY  = os.path.join(BASE_DIR, "percepcion_usuarios.gpkg")
OUT_IDW     = os.path.join(BASE_DIR, "interpolacion_idw.tif")

EPICENTER = {"lon": _cfg.EPICENTRO[0], "lat": _cfg.EPICENTRO[1], "mag": _cfg.MAGNITUD}

INTENSITY_MAP = {
    "didnt-feel": (0, "#9E9E9E"),
    "weak":       (1, "#87CEEB"),
    "moderate":   (2, "#FF8C00"),
    "strong":     (3, "#E53935"),
    "violent":    (3, "#E53935"),
}

CRS_WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")

# ══════════════════════════════════════════════════════════════════════════════
# 1. CAPA DE PERCEPCIÓN DE USUARIOS
# ══════════════════════════════════════════════════════════════════════════════
fields = QgsFields()
fields.append(QgsField("howIFelt",  QVariant.String))
fields.append(QgsField("accuracy",  QVariant.String))
fields.append(QgsField("intensity", QVariant.Int))

# Eliminar gpkg previo si existe
if os.path.exists(OUT_SURVEY):
    os.remove(OUT_SURVEY)

writer = QgsVectorFileWriter(OUT_SURVEY, "UTF-8", fields, 1, CRS_WGS84, "GPKG")

points, values = [], []
with open(CSV_PATH, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        try:
            lon = float(row["coordinates[0]"])
            lat = float(row["coordinates[1]"])
        except (ValueError, KeyError):
            continue
        felt = row.get("howIFelt", "didnt-feel")
        ival = INTENSITY_MAP.get(felt, (0,))[0]

        feat = QgsFeature(fields)
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feat.setAttributes([felt, row.get("accuracy", ""), ival])
        writer.addFeature(feat)
        points.append([lon, lat])
        values.append(ival)

del writer

survey_layer = QgsVectorLayer(OUT_SURVEY, "Percepción usuarios", "ogr")
QgsProject.instance().addMapLayer(survey_layer)

# ── Simbología categorizada ────────────────────────────────────────────────────
labels = {"didnt-feel": "No sintió", "weak": "Débil",
          "moderate": "Moderado", "strong": "Fuerte", "violent": "Violento"}
categories = []
for felt_val, (_, color_hex) in INTENSITY_MAP.items():
    sym = QgsSymbol.defaultSymbol(survey_layer.geometryType())
    ml  = QgsSimpleMarkerSymbolLayer()
    ml.setShape(QgsSimpleMarkerSymbolLayer.Square)
    ml.setSize(2.0)
    ml.setColor(QColor(color_hex))
    ml.setStrokeStyle(0)
    sym.changeSymbolLayer(0, ml)
    categories.append(QgsRendererCategory(felt_val, sym, labels.get(felt_val, felt_val)))

survey_layer.setRenderer(QgsCategorizedSymbolRenderer("howIFelt", categories))
survey_layer.triggerRepaint()

# ══════════════════════════════════════════════════════════════════════════════
# 2. INTERPOLACIÓN NEAREST NEIGHBOR
# ══════════════════════════════════════════════════════════════════════════════
pts  = np.array(points)
vals = np.array(values, dtype=float)

lon_min, lon_max = pts[:, 0].min() - 0.5, pts[:, 0].max() + 1.4
lat_min, lat_max = pts[:, 1].min() - 1.8, pts[:, 1].max() + 0.3
COLS, ROWS = 600, 400

xi = np.linspace(lon_min, lon_max, COLS)
yi = np.linspace(lat_max, lat_min, ROWS)  # norte→sur
gx, gy = np.meshgrid(xi, yi)
grid_pts = np.column_stack([gx.ravel(), gy.ravel()])

tree = cKDTree(pts)
dists, idxs = tree.query(grid_pts, k=50)
dists = np.where(dists == 0, 1e-10, dists)
weights = 1.0 / dists ** 1.5
grid = ((weights * vals[idxs]).sum(axis=1) / weights.sum(axis=1)).reshape(ROWS, COLS).astype(np.float32)

# Escribir GeoTIFF
if os.path.exists(OUT_IDW):
    os.remove(OUT_IDW)

driver = gdal.GetDriverByName("GTiff")
ds = driver.Create(OUT_IDW, COLS, ROWS, 1, gdal.GDT_Float32)
pixel_w = (lon_max - lon_min) / COLS
pixel_h = (lat_max - lat_min) / ROWS
ds.SetGeoTransform([lon_min, pixel_w, 0, lat_max, 0, -pixel_h])
srs = osr.SpatialReference()
srs.ImportFromEPSG(4326)
ds.SetProjection(srs.ExportToWkt())
ds.GetRasterBand(1).WriteArray(grid)
ds.GetRasterBand(1).SetNoDataValue(-9999)
ds.FlushCache()
ds = None

idw_layer = QgsRasterLayer(OUT_IDW, "Kriging percepción")
if not idw_layer.isValid():
    print("⚠ IDW raster no válido")
else:
    shader_func = QgsColorRampShader()
    shader_func.setColorRampType(QgsColorRampShader.Interpolated)
    shader_func.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(0.0, QColor("#9E9E9E"), "No sintió"),
        QgsColorRampShader.ColorRampItem(1.0, QColor("#87CEEB"), "Débil"),
        QgsColorRampShader.ColorRampItem(2.0, QColor("#FF8C00"), "Moderado"),
        QgsColorRampShader.ColorRampItem(3.0, QColor("#E53935"), "Fuerte"),
    ])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(shader_func)
    renderer = QgsSingleBandPseudoColorRenderer(idw_layer.dataProvider(), 1, shader)
    idw_layer.setRenderer(renderer)
    idw_layer.setOpacity(0.55)
    # No se agrega al proyecto — solo se usa para generar el clip

    # ── Clip IDW al territorio mexicano ───────────────────────────────────────
    OUT_IDW_CLIP = os.path.join(BASE_DIR, "interpolacion_idw_clip.tif")
    if os.path.exists(OUT_IDW_CLIP):
        os.remove(OUT_IDW_CLIP)

    gdal.Warp(
        OUT_IDW_CLIP, OUT_IDW,
        cutlineDSName=_cfg.SHAPE_ESTADOS,
        cropToCutline=False,   # respeta el extent actual del IDW
        dstNodata=-9999,
        outputType=gdal.GDT_Float32
    )

    idw_clip_layer = QgsRasterLayer(OUT_IDW_CLIP, "Kriging percepción (recortado)")
    if idw_clip_layer.isValid():
        # Misma simbología que el IDW original
        shader_func2 = QgsColorRampShader()
        shader_func2.setColorRampType(QgsColorRampShader.Interpolated)
        shader_func2.setColorRampItemList([
            QgsColorRampShader.ColorRampItem(0.0, QColor(158, 158, 158, 153), "No sintió"),
            QgsColorRampShader.ColorRampItem(1.0, QColor(135, 206, 235, 153), "Débil"),
            QgsColorRampShader.ColorRampItem(2.0, QColor(255, 140,   0, 153), "Moderado"),
            QgsColorRampShader.ColorRampItem(3.0, QColor(229,  57,  53, 153), "Fuerte"),
        ])
        shader2 = QgsRasterShader()
        shader2.setRasterShaderFunction(shader_func2)
        renderer2 = QgsSingleBandPseudoColorRenderer(idw_clip_layer.dataProvider(), 1, shader2)
        idw_clip_layer.setRenderer(renderer2)
        idw_clip_layer.setOpacity(1.0)
        QgsProject.instance().addMapLayer(idw_clip_layer)
        print(f"✅ IDW recortado al territorio mexicano → {OUT_IDW_CLIP}")
    else:
        print("⚠ No se pudo cargar el IDW recortado")

# ══════════════════════════════════════════════════════════════════════════════
# 3. EPICENTRO SSN
# ══════════════════════════════════════════════════════════════════════════════
epi_layer = QgsVectorLayer("Point?crs=EPSG:4326", "Epicentro SSN M5.6", "memory")
epi_prov  = epi_layer.dataProvider()
epi_prov.addAttributes([QgsField("mag", QVariant.Double)])
epi_layer.updateFields()

feat = QgsFeature()
feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(EPICENTER["lon"], EPICENTER["lat"])))
feat.setAttributes([EPICENTER["mag"]])
epi_prov.addFeature(feat)

epi_sym = QgsSymbol.defaultSymbol(epi_layer.geometryType())
epi_ml  = QgsSimpleMarkerSymbolLayer()
epi_ml.setShape(QgsSimpleMarkerSymbolLayer.Star)
epi_ml.setSize(8.0)
epi_ml.setColor(QColor("#FFD600"))
epi_ml.setStrokeColor(QColor("#000000"))
epi_ml.setStrokeWidth(0.4)
epi_sym.changeSymbolLayer(0, epi_ml)
epi_layer.setRenderer(QgsSingleSymbolRenderer(epi_sym))
QgsProject.instance().addMapLayer(epi_layer)

# ══════════════════════════════════════════════════════════════════════════════
# 4. MAPA BASE — ESRI Ocean via QuickMapServices
# ══════════════════════════════════════════════════════════════════════════════
try:
    from QuickMapServices.quick_map_services import QuickMapServices
    qms = QuickMapServices()
    qms.load_tile_layer("esri", "ocean_basemap")
    print("✅ Mapa base ESRI Ocean cargado via QuickMapServices")
except Exception as e:
    # Fallback: URL directa XYZ de ESRI Ocean
    esri_url = ("type=xyz"
                "&url=https://services.arcgisonline.com/ArcGIS/rest/services"
                "/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}"
                "&zmax=10&zmin=0&crs=EPSG3857")
    esri_layer = QgsRasterLayer(esri_url, "ESRI Ocean Basemap", "wms")
    if esri_layer.isValid():
        root = QgsProject.instance().layerTreeRoot()
        QgsProject.instance().addMapLayer(esri_layer, False)
        root.addLayer(esri_layer)
        print("✅ Mapa base ESRI Ocean cargado via XYZ")
    else:
        print(f"⚠ Mapa base no disponible: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# 5. DIVISIÓN ESTATAL MÉXICO (solo bordes)
# ══════════════════════════════════════════════════════════════════════════════
from qgis.core import QgsFillSymbol

estados_layer = QgsVectorLayer(_cfg.SHAPE_ESTADOS, "División estatal México", "ogr")
if estados_layer.isValid():
    sym = QgsFillSymbol.createSimple({
        "color": "0,0,0,0",          # relleno transparente
        "outline_color": "#424242",
        "outline_width": "0.4"
    })
    estados_layer.setRenderer(QgsSingleSymbolRenderer(sym))
    QgsProject.instance().addMapLayer(estados_layer)
    print("✅ División estatal cargada")
else:
    print("⚠ No se pudo cargar el shapefile de estados")

# ══════════════════════════════════════════════════════════════════════════════
# 6. RED SKYALERT 2026
# ══════════════════════════════════════════════════════════════════════════════
from qgis.core import QgsRasterMarkerSymbolLayer

red_layer = QgsVectorLayer("Point?crs=EPSG:4326", "REDSkyAlert 2026", "memory")
red_prov  = red_layer.dataProvider()
red_prov.addAttributes([QgsField("localidad", QVariant.String)])
red_layer.updateFields()

with open(CSV_RED, encoding="utf-8") as f:
    sensor_feats = []
    for row in csv.DictReader(f):
        try:
            lat = float(row["Lat"])
            lon = float(row["Long"])
        except (ValueError, KeyError):
            continue
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feat.setAttributes([row.get("Localidad", "")])
        sensor_feats.append(feat)

red_prov.addFeatures(sensor_feats)

# Símbolo: imagen MX.png
red_sym = QgsSymbol.defaultSymbol(red_layer.geometryType())
raster_ml = QgsRasterMarkerSymbolLayer(SENSOR_ICON)
raster_ml.setSize(6.0)
red_sym.changeSymbolLayer(0, raster_ml)
red_layer.setRenderer(QgsSingleSymbolRenderer(red_sym))
QgsProject.instance().addMapLayer(red_layer)
print(f"✅ {red_layer.featureCount()} sensores REDSkyAlert graficados")

# ══════════════════════════════════════════════════════════════════════════════
# 6. RADIOS DE ALERTAMIENTO
# ══════════════════════════════════════════════════════════════════════════════
import json as _json
from math import degrees as _deg

_CSV_RADIOS        = _cfg.CSV_RADIOS
_OUT_CIRCLES       = os.path.join(BASE_DIR, "radios_alertamiento.gpkg")
_CONFIRMING_CLUSTER = _cfg.CLUSTER_CONFIRMADOR
_CONFIRMING_GALS   = _cfg.GALS_CONFIRMACION

_INTENSITY_SCALE  = [("Débil",1,5),("Leve",5.01,21),("Moderado",21.01,35),
                     ("Fuerte",35.01,77),("Violento",77.01,156),("Severo",156.01,9999)]
_INTENSITY_COLORS = ["#87CEEB","#66BB6A","#FFD600","#FF8C00","#E53935","#B71C1C"]

def _origin_idx(gals):
    for i,(_, lo, hi) in enumerate(_INTENSITY_SCALE):
        if lo <= gals <= hi: return i
    return 0

def _circle_wkt(lat, lon, radius_km, n=180):
    from math import radians, sin, cos, degrees as _deg2
    pts = []
    for i in range(n+1):
        a = radians(360*i/n)
        dlat = (radius_km/6371)*cos(a)
        dlon = (radius_km/6371)*sin(a)/cos(radians(lat))
        pts.append(f"{lon+_deg2(dlon)} {lat+_deg2(dlat)}")
    return "POLYGON((" + ", ".join(pts) + "))"

_clusters = {}
with open(_CSV_RADIOS, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        loc = _json.loads(row["Location"])
        _clusters[row["Name"]] = {
            "lon": loc["coordinates"][0], "lat": loc["coordinates"][1],
            "grid": _json.loads(row["Grid Distances"])
        }

_oidx   = _origin_idx(_CONFIRMING_GALS)
_cl     = _clusters[_CONFIRMING_CLUSTER]
_radii  = _cl["grid"][_oidx]
_zones  = [(r, _INTENSITY_SCALE[_oidx-i][0], _INTENSITY_COLORS[_oidx-i])
           for i, r in enumerate(_radii) if 0 <= _oidx-i < len(_INTENSITY_SCALE)]

_fields = QgsFields()
_fields.append(QgsField("intensidad", QVariant.String))
_fields.append(QgsField("radio_km",   QVariant.Double))

if os.path.exists(_OUT_CIRCLES):
    os.remove(_OUT_CIRCLES)

_writer = QgsVectorFileWriter(_OUT_CIRCLES, "UTF-8", _fields, 3, CRS_WGS84, "GPKG")
for r, label, _ in reversed(_zones):
    feat = QgsFeature(_fields)
    feat.setGeometry(QgsGeometry.fromWkt(_circle_wkt(_cl["lat"], _cl["lon"], r)))
    feat.setAttributes([label, float(r)])
    _writer.addFeature(feat)
del _writer

_circles_layer = QgsVectorLayer(_OUT_CIRCLES, "Radios de alertamiento", "ogr")
_categories = []
for _, label, color_hex in _zones:
    sym = QgsFillSymbol.createSimple({
        "color": "0,0,0,0",
        "outline_color": color_hex,
        "outline_width": "0.8",
        "outline_style": "dash"
    })
    _categories.append(QgsRendererCategory(label, sym, label))
_circles_layer.setRenderer(QgsCategorizedSymbolRenderer("intensidad", _categories))
QgsProject.instance().addMapLayer(_circles_layer)
print(f"✅ {len(_zones)} radios de alertamiento agregados")

# ══════════════════════════════════════════════════════════════════════════════
# 7. ZOOM
# ══════════════════════════════════════════════════════════════════════════════
extent = QgsRectangle(lon_min, lat_min, lon_max, lat_max)
iface.mapCanvas().setExtent(extent)
iface.mapCanvas().refresh()

print(f"✅ {survey_layer.featureCount()} reportes de percepción graficados")
print(f"✅ IDW generado → {OUT_IDW}")
