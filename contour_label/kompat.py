# -*- coding: utf-8 -*-
"""
Penyesuaian antar-versi QGIS (3.22 s.d. 3.4x).

Sejak QGIS 3.30-an banyak enum dipindah ke namespace `Qgis`.
Fungsi di sini mencoba nama baru dulu, lalu nama lama.
"""


def ambil(*jalur):
    """
    Ambil atribut pertama yang ada dari beberapa jalur.
    Contoh: ambil((Qgis, "LabelPlacement", "Curved"),
                  (QgsPalLayerSettings, "Curved"))
    """
    for item in jalur:
        objek = item[0]
        try:
            for nama in item[1:]:
                objek = getattr(objek, nama)
            return objek
        except AttributeError:
            continue
    raise AttributeError("Tidak ada atribut yang cocok: %r" % (jalur,))
