# -*- coding: utf-8 -*-
"""
Orientasi garis kontur agar label menghadap ke atas lereng.

Prinsip: pada label yang mengikuti arah garis, bagian ATAS teks berada
di sisi KIRI arah garis. Jadi setiap garis diarahkan sehingga tanah yang
lebih tinggi berada di sebelah kirinya; bila tidak, urutan titiknya
dibalik (bentuk garis tidak berubah).

Sisi yang lebih tinggi ditentukan dengan dua cara:
- PenilaiDEM      : mengambil nilai DEM sedikit di kiri dan kanan garis.
- PenilaiTetangga : tanpa DEM, menembakkan "sinar" tegak lurus garis ke
                    kiri dan kanan, lalu melihat ketinggian kontur
                    terdekat yang dikenai.
Keduanya menilai beberapa titik sepanjang garis lalu mengambil suara
terbanyak, sehingga tahan terhadap gangguan lokal.
"""

import math

from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsCsException,
    QgsGeometry,
    QgsLineString,
    QgsPointXY,
    QgsRectangle,
    QgsSpatialIndex,
    QgsWkbTypes,
)

from .kompat import ambil

FRAKSI_SAMPEL = (0.1, 0.3, 0.5, 0.7, 0.9)


# ---- geometri ---------------------------------------------------------------
def bagian_garis(geom):
    """Daftar bagian (QgsLineString) dari geometri garis tunggal/multi."""
    if geom is None or geom.isEmpty():
        return []
    g = geom.constGet()
    if QgsWkbTypes.isMultiType(geom.wkbType()):
        bagian = [g.geometryN(i) for i in range(g.numGeometries())]
    else:
        bagian = [g]
    # Selalu salinan: bagian milik geometri asli bisa ikut terhapus
    # bersama geometrinya dan membuat QGIS crash bila dipakai belakangan.
    hasil = []
    for b in bagian:
        if isinstance(b, QgsLineString):
            hasil.append(b.clone())
        else:
            hasil.append(b.curveToLine())
    return hasil


def susun_geometri(geom_asli, bagian):
    """Bangun ulang geometri dengan tipe (tunggal/multi, Z/M) yang sama."""
    if QgsWkbTypes.isMultiType(geom_asli.wkbType()):
        multi = geom_asli.constGet().createEmptyWithSameType()
        for b in bagian:
            multi.addGeometry(b.clone())
        return QgsGeometry(multi)
    return QgsGeometry(bagian[0].clone())


def titik_sampel(bagian):
    """[(titik, normal_kiri)] pada beberapa posisi sepanjang garis."""
    g = QgsGeometry(bagian.clone())
    panjang = g.length()
    if panjang <= 0:
        return []
    hasil = []
    for f in FRAKSI_SAMPEL:
        jarak = panjang * f
        titik = g.interpolate(jarak)
        if titik.isEmpty():
            continue
        sudut = g.interpolateAngle(jarak)  # radian, searah jarum jam dari utara
        # arah garis = (sin a, cos a); kiri = putar 90 derajat berlawanan jarum jam
        hasil.append((titik.asPoint(), (-math.cos(sudut), math.sin(sudut))))
    return hasil


def _geser(p, n, d):
    return QgsPointXY(p.x() + n[0] * d, p.y() + n[1] * d)


# ---- penilai berbasis DEM ---------------------------------------------------
class PenilaiDEM:

    def __init__(self, raster, crs_layer, konteks_transformasi, band=1):
        self.prov = raster.dataProvider()
        self.band = band
        self.xf = QgsCoordinateTransform(crs_layer, raster.crs(), konteks_transformasi)
        balik = ambil((Qgis, "TransformDirection", "Reverse"),
                      (QgsCoordinateTransform, "ReverseTransform"))
        try:
            ext = self.xf.transformBoundingBox(raster.extent(), balik)
        except QgsCsException:
            ext = raster.extent()
        lebar_px = ext.width() / max(raster.width(), 1)
        tinggi_px = ext.height() / max(raster.height(), 1)
        # Ambil sampel 1,5 piksel dari garis: cukup dekat agar tidak
        # melewati kontur berikutnya, cukup jauh agar beda nilainya nyata.
        self.jarak = 1.5 * max(lebar_px, tinggi_px)

    def _nilai(self, p):
        try:
            q = self.xf.transform(p)
            v, ok = self.prov.sample(q, self.band)
        except QgsCsException:
            return None
        if not ok or v is None or math.isnan(v):
            return None
        return v

    def skor(self, bagian, elev, _indeks=None):
        """>0: sisi kiri lebih tinggi; <0: sisi kanan lebih tinggi; 0: tak tentu."""
        s = 0
        for p, n in titik_sampel(bagian):
            kiri = self._nilai(_geser(p, n, self.jarak))
            kanan = self._nilai(_geser(p, n, -self.jarak))
            if kiri is None or kanan is None or kiri == kanan:
                continue
            s += 1 if kiri > kanan else -1
        return s


# ---- penilai berbasis kontur tetangga ---------------------------------------
class PenilaiTetangga:

    def __init__(self, daftar):
        """daftar: [(QgsLineString bagian, elev)]"""
        self.daftar = [(QgsGeometry(b.clone()), e) for b, e in daftar]
        self.indeks = QgsSpatialIndex()
        ext = None
        for i, (g, _) in enumerate(self.daftar):
            kotak = g.boundingBox()
            self.indeks.addFeature(i, kotak)
            if ext is None:
                ext = QgsRectangle(kotak)
            else:
                ext.combineExtentWith(kotak)
        diag = math.hypot(ext.width(), ext.height()) if ext is not None else 0
        self.r_awal = max(diag * 0.004, 1e-9)
        self.r_maks = max(diag * 0.25, self.r_awal)

    def _kontur_terdekat(self, p, n, elev):
        """
        Elevasi kontur pertama yang dikenai sinar dari p ke arah n.
        Bila yang pertama dikenai adalah kontur senilai (termasuk garis itu
        sendiri, mis. sinar ke dalam lingkaran puncak), sisi ini dianggap
        tak memberi informasi (None).
        """
        r = self.r_awal
        mulai = _geser(p, n, self.r_awal * 0.01)  # hindari titik asal di garis
        asal = QgsGeometry.fromPointXY(p)
        while r <= self.r_maks:
            sinar = QgsGeometry.fromPolylineXY([mulai, _geser(p, n, r)])
            terbaik = None
            for j in self.indeks.intersects(sinar.boundingBox()):
                g, e = self.daftar[j]
                if not g.intersects(sinar):
                    continue
                jarak = g.intersection(sinar).distance(asal)
                if terbaik is None or jarak < terbaik[0]:
                    terbaik = (jarak, e)
            if terbaik is not None:
                return None if abs(terbaik[1] - elev) < 1e-9 else terbaik[1]
            r *= 4
        return None

    def skor(self, bagian, elev, _indeks=None):
        s = 0
        for p, n in titik_sampel(bagian):
            kiri = self._kontur_terdekat(p, n, elev)
            kanan = self._kontur_terdekat(p, (-n[0], -n[1]), elev)
            if kiri is not None:
                s += 1 if kiri > elev else -1
            if kanan is not None:
                s += 1 if kanan < elev else -1
        return s
