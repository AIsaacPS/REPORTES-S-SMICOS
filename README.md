# SkyAlert Evaluation — Sistema de Evaluación de Alertas Sísmicas

Herramientas para evaluar el desempeño del sistema de alerta temprana SkyAlert a partir del reporte preliminar del sismo (TXT o HTML) y la encuesta de percepción de usuarios (CSV).

---

## Estructura del proyecto

```
SKYALERT-EVALUATION/
├── README.md
├── parse_reporte.py              ← Parser de reporte (TXT o HTML) → genera config.py
├── analisis_desempeno.py         ← Gráfico estadístico (4 subplots)
├── mapa_evaluacion.py            ← Mapa de percepción en QGIS
│
├── assets/                       ← Recursos fijos (no modificar por sismo)
│   ├── RadiosDeAlertamiento.csv
│   ├── REDSkyAlert_2026.csv
│   ├── MX.png
│   ├── Logo_SkyAlert_Negro.png
│   └── Division_estatal/
│       └── dest23cw.*            ← Shapefile de límites estatales
│
└── sismos/                       ← Un subdirectorio por evento sísmico
    └── YYYY-MM-DD_HHMMSS/        ← Fecha y hora de confirmación SkyAlert
        ├── reporte.txt           ← Input: reporte preliminar del sismo
        ├── encuesta.csv          ← Input: encuesta de percepción de usuarios
        ├── config.py             ← Auto-generado por parse_reporte.py
        └── output/               ← Archivos generados
            ├── evaluacion_desempeno.png
            ├── percepcion_usuarios.gpkg
            ├── radios_alertamiento.gpkg
            ├── interpolacion_idw.tif
            └── interpolacion_idw_clip.tif
```

---

## Inputs requeridos por sismo

| Archivo | Descripción |
|---|---|
| Reporte preliminar (`.txt` o `.html`) | Borrador del reporte técnico del sismo con datos de detección |
| Encuesta CSV | Respuestas de percepción de usuarios SkyAlert |

Los archivos fijos en `assets/` se actualizan solo cuando cambian los parámetros operativos de la red.

---

## Flujo de trabajo

### Paso 1 — Parsear el reporte y crear la carpeta del sismo

```bash
cd SKYALERT-EVALUATION/
python3 parse_reporte.py <reporte.txt> <encuesta.csv>
```

Ejemplo:

```bash
python3 parse_reporte.py reporte_preliminar.txt encuesta-04-05-2026.csv
```

Esto automáticamente:
- Crea la carpeta `sismos/YYYY-MM-DD_HHMMSS/` con subcarpeta `output/`
- Copia el reporte y la encuesta a la carpeta del sismo
- Genera `config.py` con los parámetros extraídos (epicentro, magnitud, cluster confirmador, Lc, etc.)

### Paso 2 — Generar el gráfico de análisis estadístico

```bash
python3 analisis_desempeno.py sismos/YYYY-MM-DD_HHMMSS/
```

Genera `output/evaluacion_desempeno.png` con 4 subplots:

1. **Percepción del sismo** — Donut de distribución `howIFelt`
2. **¿Consideras que debimos alertarte?** — Donut de expectativa de alerta
3. **Percepción por zona de alertamiento** — Barras apiladas vs radios del cluster confirmador
4. **Distribución temporal de respuestas** — KDE de hora de respuesta

### Paso 3 — Generar el mapa de percepción en QGIS

Abrir QGIS → Complementos → Consola de Python y ejecutar:

```python
SISMO_DIR = '/ruta/completa/a/sismos/YYYY-MM-DD_HHMMSS'
exec(Path('/ruta/completa/a/SKYALERT-EVALUATION/mapa_evaluacion.py').read_text())
```

Genera las siguientes capas (de fondo a frente):

| Capa | Descripción |
|---|---|
| ESRI Ocean Basemap | Mapa base |
| Interpolación IDW (recortada) | Percepción interpolada al territorio mexicano |
| División estatal | Límites políticos (solo bordes) |
| REDSkyAlert 2026 | Sensores de la red (ícono MX.png) |
| Radios de alertamiento | Círculos por intensidad (borde punteado) |
| Percepción usuarios | Cuadros coloreados por nivel de percepción |
| Epicentro SSN | Estrella amarilla |

---

## Escala de intensidades SkyAlert

| Intensidad | Rango (gals) | Color |
|---|---|---|
| Débil | 1.0 – 5.0 | Azul cielo |
| Leve | 5.01 – 21.0 | Verde |
| Moderado | 21.01 – 35.0 | Amarillo |
| Fuerte | 35.01 – 77.0 | Naranja |
| Violento | 77.01 – 156.0 | Rojo |
| Severo | > 156.0 | Rojo oscuro |

---

## Notas

- La **Latencia de confirmación (Lc)** se calcula como: `hora_confirmación_SkyAlert − hora_origen_SSN − 1.0 s`
- `parse_reporte.py` soporta tanto TXT (formato de reporte preliminar) como HTML (reporte REDSkyAlert legacy)
- Los scripts `analisis_desempeno.py` y `mapa_evaluacion.py` viven en la raíz y **no se copian** a cada sismo; reciben la carpeta del sismo como argumento
- La interpolación IDW usa `k=50` vecinos y exponente `1.5` (ajustable en `mapa_evaluacion.py`)
- Los archivos en `assets/` deben actualizarse cuando cambien los parámetros operativos de la red
