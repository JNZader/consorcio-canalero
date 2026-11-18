"""Informe de área — static map rendering (T2, NOT YET IMPLEMENTED).

TODO(T2): contorno de la selección, subcuencas, escala gráfica, norte y
leyenda per S7 — Pillow paints the ``class_breaks.py`` palette over the
rasterio clip, ReportLab draws the vector overlay. Fondo: nada o una
miniatura Sentinel-2 vía GEE; NUNCA Esri (map stack policy, AGENTS.md:
Esri imagery is banned in derived products).

The module exists now so T1's imports are stable while the builder lands.
"""

from __future__ import annotations
