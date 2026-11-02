# -*- coding: utf-8 -*-
"""
Logika inti Contour Label (murni Python, tanpa ketergantungan QGIS).

Berisi:
- deteksi field ketinggian dari nama/alias,
- konversi nilai ketinggian (angka atau teks) ke float,
- deteksi interval kontur,
- klasifikasi mayor/minor,
- format teks label.
"""

import math
import re
from collections import Counter
from functools import reduce

# Skala bilangan bulat untuk perhitungan interval (presisi 0,001 m)
_SKALA = 1000

# Kata kunci field ketinggian. Bobot lebih tinggi = lebih meyakinkan.
_KATA_KUAT = {
    "elev", "elevation", "elevasi", "ele", "ketinggian", "tinggi",
    "height", "nilai", "alt", "altitude", "hgt", "z", "nilkon",
    "contour_value", "level",
}
_AWALAN_KUAT = ("elev", "tinggi", "ketinggian", "nilkon", "height", "altit")
_KATA_LEMAH = {"kontur", "contour", "garis", "kon"}

# Field yang tidak mungkin berisi ketinggian
_DIKECUALIKAN = {
    "fid", "id", "objectid", "object_id", "gid", "ogc_fid", "shape_length",
    "shape_len", "shape_leng", "length", "panjang",
}

_POLA_ANGKA = re.compile(r"-?\d+(?:[.,]\d+)?")


def _token(teks):
    return [t for t in re.split(r"[^a-z0-9]+", (teks or "").lower()) if t]


def skor_nama_field(nama, alias=""):
    """Skor seberapa mirip nama/alias sebuah field dengan field ketinggian."""
    nama_l = (nama or "").lower()
    if nama_l in _DIKECUALIKAN:
        return 0
    skor = 0
    for teks in (nama, alias):
        for tok in _token(teks):
            if tok in _KATA_KUAT or tok.startswith(_AWALAN_KUAT):
                skor = max(skor, 3)
            elif tok in _KATA_LEMAH:
                skor = max(skor, 1)
    return skor


def ke_angka(nilai):
    """
    Ubah nilai atribut menjadi float. Mengembalikan None bila kosong
    atau tidak bisa dibaca. Menerima angka, teks ("1220", "1220 m",
    "12,5"), dan nilai NULL QGIS.
    """
    if nilai is None:
        return None
    # NULL QGIS (QVariant) memiliki isNull()
    is_null = getattr(nilai, "isNull", None)
    if callable(is_null):
        try:
            if is_null():
                return None
        except TypeError:
            pass
    if isinstance(nilai, bool):
        return None
    if isinstance(nilai, (int, float)):
        if isinstance(nilai, float) and (math.isnan(nilai) or math.isinf(nilai)):
            return None
        return float(nilai)
    teks = str(nilai).strip()
    if not teks or teks.upper() in ("NULL", "NONE", "NAN"):
        return None
    cocok = _POLA_ANGKA.search(teks)
    if not cocok:
        return None
    try:
        return float(cocok.group(0).replace(",", "."))
    except ValueError:
        return None


def pilih_field_ketinggian(kandidat):
    """
    kandidat: list of dict {nama, alias, jumlah_valid}
    Mengembalikan nama field terbaik atau None.
    Field yang nilainya kosong semua (misalnya 'Jenis Garis Kontur'
    pada RBI) otomatis tersisih.
    """
    terbaik = None
    kunci_terbaik = None
    for k in kandidat:
        skor = skor_nama_field(k["nama"], k.get("alias", ""))
        if skor == 0 or k.get("jumlah_valid", 0) == 0:
            continue
        kunci = (skor, k.get("jumlah_valid", 0))
        if kunci_terbaik is None or kunci > kunci_terbaik:
            kunci_terbaik = kunci
            terbaik = k["nama"]
    return terbaik


def _ke_int(nilai):
    return int(round(nilai * _SKALA))


def deteksi_interval(nilai_list):
    """
    Deteksi interval kontur dari kumpulan nilai ketinggian.

    Mengembalikan dict:
      interval : float atau None
      offset   : float (sisa nilai terhadap interval, biasanya 0)
      campuran : True bila pola selisih tidak seragam
      fpb      : FPB seluruh selisih (untuk informasi)
      jumlah_unik : banyaknya nilai unik
    """
    unik = sorted({_ke_int(v) for v in nilai_list if v is not None})
    hasil = {"interval": None, "offset": 0.0, "campuran": False,
             "fpb": None, "jumlah_unik": len(unik), "menyimpang": []}
    if len(unik) < 2:
        return hasil

    selisih = [b - a for a, b in zip(unik, unik[1:]) if b - a > 0]
    if not selisih:
        return hasil

    fpb = reduce(math.gcd, selisih)
    modus = Counter(selisih).most_common(1)[0][0]
    hasil["fpb"] = fpb / _SKALA
    hasil["menyimpang"] = []

    # 1) FPB dianggap interval bila sebagian besar jenjang terisi.
    #    Data kontur yang wajar (meski terpotong) mengisi hampir semua
    #    jenjang dari nilai terendah sampai tertinggi.
    jenjang = (unik[-1] - unik[0]) // fpb + 1
    if len(unik) / jenjang >= 0.5:
        hasil["interval"] = fpb / _SKALA
        hasil["offset"] = (unik[0] % fpb) / _SKALA
        return hasil

    # 2) Ada beberapa nilai nyasar (mis. 1007 di data 10 m): pakai selisih
    #    yang paling sering muncul bila hampir semua nilai jatuh di gridnya.
    if modus != fpb:
        sisa = Counter(v % modus for v in unik)
        offset_dominan, jumlah = sisa.most_common(1)[0]
        if jumlah / len(unik) >= 0.95:
            hasil["interval"] = modus / _SKALA
            hasil["offset"] = offset_dominan / _SKALA
            hasil["menyimpang"] = [v / _SKALA for v in unik
                                   if v % modus != offset_dominan]
            return hasil

    # 3) Interval campuran (mis. gabungan lembar 12,5 m dan 10 m).
    hasil["campuran"] = True
    hasil["interval"] = modus / _SKALA
    hasil["offset"] = 0.0
    return hasil


def adalah_mayor(nilai, interval_mayor, offset=0.0):
    """True bila nilai jatuh tepat pada kelipatan interval mayor."""
    if nilai is None or not interval_mayor:
        return False
    v = _ke_int(nilai) - _ke_int(offset)
    m = _ke_int(interval_mayor)
    return m != 0 and v % m == 0


def format_label(nilai, akhiran=""):
    """1005.0 -> '1005'; 12.5 -> '12.5'; dengan akhiran opsional."""
    if nilai is None:
        return None
    if abs(nilai - round(nilai)) < 1e-6:
        teks = str(int(round(nilai)))
    else:
        teks = ("%.3f" % nilai).rstrip("0").rstrip(".")
    if akhiran:
        teks = teks + akhiran
    return teks


def label_numerik(nilai):
    """Nilai label untuk field label bertipe angka."""
    if nilai is None:
        return None
    if abs(nilai - round(nilai)) < 1e-6:
        return int(round(nilai))
    return round(nilai, 3)
