# -*- coding: utf-8 -*-
"""Style garis dan label siap pakai untuk layer kontur."""

from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsLabeling,
    QgsLineSymbol,
    QgsPalLayerSettings,
    QgsRendererCategory,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayerSimpleLabeling,
)

from .kompat import ambil

WARNA_KONTUR = "139,90,43,255"     # cokelat kontur
WARNA_LABEL = QColor(110, 70, 30)
TEBAL_MAYOR = 0.45                  # mm
TEBAL_MINOR = 0.18                  # mm
JARAK_ULANG_LABEL = 80              # mm di layar/cetak


def _mm():
    return ambil((Qgis, "RenderUnit", "Millimeters"),
                 (QgsUnitTypes, "RenderMillimeters"))


def _garis(tebal, warna=WARNA_KONTUR, putus=False):
    props = {
        "line_color": warna,
        "line_width": str(tebal),
        "line_width_unit": "MM",
        "capstyle": "round",
        "joinstyle": "round",
    }
    if putus:
        props["line_style"] = "dash"
    return QgsLineSymbol.createSimple(props)


def terapkan_renderer(layer, field_indeks, indeks_numerik=True, ada_tanpa_nilai=False):
    nilai_mayor = 1 if indeks_numerik else "1"
    nilai_minor = 0 if indeks_numerik else "0"
    kategori = [
        QgsRendererCategory(nilai_mayor, _garis(TEBAL_MAYOR), "Kontur mayor (indeks)"),
        QgsRendererCategory(nilai_minor, _garis(TEBAL_MINOR), "Kontur minor"),
    ]
    if ada_tanpa_nilai:
        # Kategori kosong = "semua nilai lain", termasuk NULL
        kategori.append(QgsRendererCategory(
            "", _garis(TEBAL_MINOR, "150,150,150,255", True), "Tanpa nilai ketinggian"))
    layer.setRenderer(QgsCategorizedSymbolRenderer(field_indeks, kategori))


def terapkan_label(layer, field_label, ikuti_arah_garis=False):
    s = QgsPalLayerSettings()
    s.fieldName = field_label
    s.isExpression = False
    s.drawLabels = True

    # Label melengkung mengikuti garis, tepat di atas garis
    s.placement = ambil((Qgis, "LabelPlacement", "Curved"),
                        (QgsPalLayerSettings, "Curved"))
    ls = s.lineSettings()
    ls.setPlacementFlags(QgsLabeling.LinePlacementFlag.OnLine)
    s.setLineSettings(ls)

    # Ulangi label sepanjang garis panjang (letak API berbeda antar-versi QGIS)
    ls = s.lineSettings()
    if hasattr(ls, "setRepeatDistance"):
        ls.setRepeatDistance(JARAK_ULANG_LABEL)
        ls.setRepeatDistanceUnit(_mm())
        s.setLineSettings(ls)
    elif hasattr(s, "repeatDistance"):
        s.repeatDistance = JARAK_ULANG_LABEL
        s.repeatDistanceUnit = _mm()

    if ikuti_arah_garis:
        # Label mengikuti arah garis apa adanya (boleh terbalik), sehingga
        # bagian atas angka selalu di sisi kiri garis = sisi atas lereng.
        s.upsidedownLabels = ambil(
            (Qgis, "UpsideDownLabelHandling", "AlwaysAllowUpsideDown"),
            (QgsPalLayerSettings, "ShowAll"))

    fmt = QgsTextFormat()
    font = QFont("Arial")
    font.setBold(False)
    fmt.setFont(font)
    fmt.setSize(7.5)
    fmt.setSizeUnit(ambil((Qgis, "RenderUnit", "Points"),
                          (QgsUnitTypes, "RenderPoints")))
    fmt.setColor(WARNA_LABEL)

    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    buf.setSizeUnit(_mm())
    buf.setColor(QColor(255, 255, 255))
    buf.setOpacity(0.9)
    fmt.setBuffer(buf)
    s.setFormat(fmt)

    layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
    layer.setLabelsEnabled(True)


def terapkan(layer, field_indeks, field_label, indeks_numerik=True,
             ikuti_arah_garis=False, ada_tanpa_nilai=False):
    terapkan_renderer(layer, field_indeks, indeks_numerik, ada_tanpa_nilai)
    terapkan_label(layer, field_label, ikuti_arah_garis)
    if hasattr(layer, "emitStyleChanged"):
        layer.emitStyleChanged()
    layer.triggerRepaint()
