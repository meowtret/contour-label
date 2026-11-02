# -*- coding: utf-8 -*-
"""Algoritma Processing: isi atribut indeks (mayor/minor) dan label kontur."""

import os

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    Qgis,
    QgsFeatureRequest,
    QgsField,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputNumber,
    QgsProcessingOutputVectorLayer,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
)

from . import core
from .kompat import ambil

SAMPEL_DETEKSI = 2000


def _tr(teks):
    return QCoreApplication.translate("ContourLabel", teks)


def _lanjutan(param):
    flag = ambil((Qgis, "ProcessingParameterFlag", "Advanced"),
                 (QgsProcessingParameterDefinition, "FlagAdvanced"))
    param.setFlags(param.flags() | flag)
    return param


def _tipe_double():
    return ambil((Qgis, "ProcessingNumberParameterType", "Double"),
                 (QgsProcessingParameterNumber, "Double"))


def _tipe_integer():
    return ambil((Qgis, "ProcessingNumberParameterType", "Integer"),
                 (QgsProcessingParameterNumber, "Integer"))


def _tanpa_geometri():
    return ambil((Qgis, "FeatureRequestFlag", "NoGeometry"),
                 (QgsFeatureRequest, "NoGeometry"))


def _field_baru(nama, tipe):
    """QgsField kompatibel QGIS 3.22-3.4x (QVariant) dan versi baru (QMetaType)."""
    try:
        from qgis.PyQt.QtCore import QMetaType
        tipe_meta = {"int": QMetaType.Type.Int, "str": QMetaType.Type.QString}[tipe]
        return QgsField(nama, tipe_meta, len=0 if tipe == "int" else 20)
    except (ImportError, AttributeError, TypeError):
        tipe_var = {"int": QVariant.Int, "str": QVariant.String}[tipe]
        return QgsField(nama, tipe_var, len=0 if tipe == "int" else 20)


class ContourLabelAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    FIELD_ELEV = "FIELD_ELEV"
    INTERVAL = "INTERVAL"
    KELIPATAN = "KELIPATAN"
    INTERVAL_MAYOR = "INTERVAL_MAYOR"
    FIELD_INDEKS = "FIELD_INDEKS"
    FIELD_LABEL = "FIELD_LABEL"
    AKHIRAN = "AKHIRAN"
    TERAPKAN_STYLE = "TERAPKAN_STYLE"
    ORIENTASI = "ORIENTASI"
    DEM = "DEM"

    # ---- identitas ------------------------------------------------------
    def name(self):
        return "isi_label_kontur"

    def displayName(self):
        return _tr("Isi indeks & label kontur")

    def group(self):
        return ""

    def groupId(self):
        return ""

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))

    def createInstance(self):
        return ContourLabelAlgorithm()

    def flags(self):
        # Mengubah layer di proyek dan style-nya harus di thread utama
        try:
            return super().flags() | Qgis.ProcessingAlgorithmFlag.NoThreading
        except AttributeError:
            return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        return _tr(
            "<p>Mengisi atribut kontur secara otomatis langsung di layer "
            "masukan:</p>"
            "<ul>"
            "<li><b>indeks</b>: 1 untuk garis mayor, 0 untuk garis minor</li>"
            "<li><b>label</b>: angka ketinggian untuk garis mayor, kosong "
            "(NULL) untuk garis minor</li>"
            "</ul>"
            "<p>Field ketinggian dan interval kontur dideteksi otomatis "
            "(cocok untuk kontur DEMNAS hasil GDAL Contour, RBI, maupun OSM). "
            "Garis mayor ditentukan dari <i>interval × kelipatan</i>, "
            "misalnya interval 10 m × 5 = mayor setiap 50 m.</p>"
            "<p>Bila interval data tidak seragam (mis. gabungan lembar RBI "
            "beda skala), isi <b>Interval mayor</b> secara manual pada "
            "parameter lanjutan.</p>"
            "<p><b>Orientasi label ke atas lereng</b> (opsional): arah garis "
            "dibalik bila perlu sehingga bagian atas angka label menghadap ke "
            "tanah yang lebih tinggi. Arah lereng dibaca dari DEM bila diisi, "
            "atau dari kontur tetangga bila DEM dikosongkan. Bentuk garis tidak "
            "berubah, hanya urutan titiknya.</p>"
            "<p>Field yang belum ada akan dibuat. Perubahan langsung "
            "disimpan, kecuali layer sedang dalam mode edit.</p>"
        )

    # ---- parameter ------------------------------------------------------
    def initAlgorithm(self, config=None):
        tipe_garis = ambil((Qgis, "ProcessingSourceType", "VectorLine"),
                           (QgsProcessing, "TypeVectorLine"))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, _tr("Layer kontur (garis)"), [tipe_garis]))

        self.addParameter(QgsProcessingParameterField(
            self.FIELD_ELEV,
            _tr("Field ketinggian (kosongkan = deteksi otomatis)"),
            parentLayerParameterName=self.INPUT,
            optional=True))

        self.addParameter(QgsProcessingParameterNumber(
            self.INTERVAL,
            _tr("Interval kontur, meter (0 = deteksi otomatis)"),
            type=_tipe_double(), defaultValue=0, minValue=0))

        self.addParameter(QgsProcessingParameterNumber(
            self.KELIPATAN,
            _tr("Garis mayor setiap … garis (kelipatan)"),
            type=_tipe_integer(), defaultValue=5, minValue=1))

        self.addParameter(QgsProcessingParameterBoolean(
            self.TERAPKAN_STYLE,
            _tr("Terapkan style garis dan label otomatis"),
            defaultValue=True))

        self.addParameter(QgsProcessingParameterBoolean(
            self.ORIENTASI,
            _tr("Orientasikan label ke atas lereng (membalik arah garis bila perlu)"),
            defaultValue=False))

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.DEM,
            _tr("DEM untuk arah lereng (opsional; kosong = pakai kontur tetangga)"),
            optional=True))

        self.addParameter(_lanjutan(QgsProcessingParameterNumber(
            self.INTERVAL_MAYOR,
            _tr("Interval mayor, meter (0 = interval × kelipatan)"),
            type=_tipe_double(), defaultValue=0, minValue=0)))

        self.addParameter(_lanjutan(QgsProcessingParameterString(
            self.FIELD_INDEKS, _tr("Nama field indeks"), defaultValue="indeks")))

        self.addParameter(_lanjutan(QgsProcessingParameterString(
            self.FIELD_LABEL, _tr("Nama field label"), defaultValue="label")))

        self.addParameter(_lanjutan(QgsProcessingParameterString(
            self.AKHIRAN, _tr("Akhiran label (mis. \" m\"), opsional"),
            defaultValue="", optional=True)))

        self.addOutput(QgsProcessingOutputVectorLayer(
            "OUTPUT", _tr("Layer kontur")))
        for kode, judul in (
                ("INTERVAL_TERPAKAI", "Interval kontur"),
                ("INTERVAL_MAYOR_TERPAKAI", "Interval mayor"),
                ("JUMLAH_MAYOR", "Jumlah garis mayor"),
                ("JUMLAH_MINOR", "Jumlah garis minor"),
                ("JUMLAH_KOSONG", "Jumlah garis tanpa nilai"),
                ("JUMLAH_DIBALIK", "Jumlah garis yang arahnya dibalik"),
                ("JUMLAH_TAK_TENTU", "Jumlah garis yang arahnya tak terpastikan")):
            self.addOutput(QgsProcessingOutputNumber(kode, _tr(judul)))

    # ---- bantuan --------------------------------------------------------
    def _field_terpilih(self, parameters, context):
        try:
            daftar = self.parameterAsStrings(parameters, self.FIELD_ELEV, context)
        except AttributeError:
            daftar = self.parameterAsFields(parameters, self.FIELD_ELEV, context)
        return daftar[0] if daftar else None

    def _deteksi_field(self, layer, dikecualikan):
        fields = layer.fields()
        calon = [f for f in fields if f.name() not in dikecualikan]
        hitung = {f.name(): 0 for f in calon}
        req = QgsFeatureRequest().setFlags(_tanpa_geometri()).setLimit(SAMPEL_DETEKSI)
        for feat in layer.getFeatures(req):
            for f in calon:
                if core.ke_angka(feat[f.name()]) is not None:
                    hitung[f.name()] += 1
        kandidat = [{"nama": f.name(), "alias": f.alias(),
                     "jumlah_valid": hitung[f.name()]} for f in calon]
        return core.pilih_field_ketinggian(kandidat)

    # ---- proses ---------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        if layer is None:
            raise QgsProcessingException(_tr("Layer masukan tidak ditemukan."))

        nama_indeks = (self.parameterAsString(parameters, self.FIELD_INDEKS, context) or "indeks").strip()
        nama_label = (self.parameterAsString(parameters, self.FIELD_LABEL, context) or "label").strip()
        akhiran = self.parameterAsString(parameters, self.AKHIRAN, context) or ""
        if nama_indeks == nama_label:
            raise QgsProcessingException(_tr("Nama field indeks dan label harus berbeda."))

        # 1. Field ketinggian
        field_elev = self._field_terpilih(parameters, context)
        if not field_elev:
            field_elev = self._deteksi_field(layer, {nama_indeks, nama_label})
            if not field_elev:
                raise QgsProcessingException(_tr(
                    "Field ketinggian tidak terdeteksi. Pilih field ketinggian "
                    "secara manual pada parameter 'Field ketinggian'."))
            alias = layer.fields().field(field_elev).alias()
            feedback.pushInfo(_tr("Field ketinggian terdeteksi: {}{}").format(
                field_elev, " ({})".format(alias) if alias and alias != field_elev else ""))
        if field_elev in (nama_indeks, nama_label):
            raise QgsProcessingException(_tr(
                "Field ketinggian tidak boleh sama dengan field indeks/label."))

        # 2. Baca nilai ketinggian
        req = QgsFeatureRequest().setFlags(_tanpa_geometri())
        req.setSubsetOfAttributes([field_elev], layer.fields())
        nilai = {}
        for feat in layer.getFeatures(req):
            if feedback.isCanceled():
                return {}
            nilai[feat.id()] = core.ke_angka(feat[field_elev])

        valid = [v for v in nilai.values() if v is not None]
        if not valid:
            raise QgsProcessingException(_tr(
                "Field '{}' tidak berisi nilai ketinggian yang bisa dibaca.").format(field_elev))
        jumlah_kosong = len(nilai) - len(valid)
        if jumlah_kosong:
            feedback.pushWarning(_tr(
                "{} garis tidak punya nilai ketinggian yang terbaca; "
                "indeks dan label-nya dikosongkan.").format(jumlah_kosong))

        # 3. Interval
        interval_manual = self.parameterAsDouble(parameters, self.INTERVAL, context)
        kelipatan = self.parameterAsInt(parameters, self.KELIPATAN, context)
        mayor_manual = self.parameterAsDouble(parameters, self.INTERVAL_MAYOR, context)

        det = core.deteksi_interval(valid)
        if interval_manual > 0:
            interval = interval_manual
            offset = 0.0
        else:
            interval = det["interval"]
            offset = det["offset"]
            if interval is None:
                raise QgsProcessingException(_tr(
                    "Interval tidak bisa dideteksi (nilai ketinggian kurang "
                    "dari dua jenjang). Isi interval secara manual."))
            if det["campuran"] and mayor_manual <= 0:
                raise QgsProcessingException(_tr(
                    "Interval kontur pada data ini tidak seragam (FPB selisih "
                    "{} m). Kemungkinan gabungan data dengan interval berbeda. "
                    "Isi 'Interval mayor' secara manual pada parameter "
                    "lanjutan, misalnya 50 atau 100.").format(
                        core.format_label(det["fpb"])))
            if det["campuran"]:
                feedback.pushWarning(_tr(
                    "Interval kontur tidak seragam; klasifikasi memakai "
                    "interval mayor manual."))
            else:
                feedback.pushInfo(_tr("Interval terdeteksi: {} m").format(
                    core.format_label(interval)))
            if det["menyimpang"]:
                contoh = ", ".join(core.format_label(v) for v in det["menyimpang"][:10])
                feedback.pushWarning(_tr(
                    "{} nilai ketinggian tidak berada pada grid interval "
                    "(contoh: {}). Garis tersebut tetap diproses sebagai minor.").format(
                        len(det["menyimpang"]), contoh))

        if mayor_manual > 0:
            interval_mayor = mayor_manual
            offset = 0.0
        else:
            interval_mayor = interval * kelipatan
        if offset:
            feedback.pushInfo(_tr("Nilai kontur bergeser {} m dari kelipatan "
                                  "interval; garis mayor mengikuti pergeseran ini.")
                              .format(core.format_label(offset)))
        feedback.pushInfo(_tr("Garis mayor setiap {} m.").format(
            core.format_label(interval_mayor)))

        orientasi = self.parameterAsBoolean(parameters, self.ORIENTASI, context)
        dem = self.parameterAsRasterLayer(parameters, self.DEM, context) if orientasi else None
        if orientasi:
            feedback.pushInfo(_tr("Arah lereng dibaca dari {}.").format(
                _tr("DEM '{}'").format(dem.name()) if dem else _tr("kontur tetangga")))

        # 4. Siapkan field & mode edit
        sedang_edit = layer.isEditable()
        if not sedang_edit and not layer.startEditing():
            raise QgsProcessingException(_tr(
                "Layer tidak bisa diedit (read-only). Simpan dulu sebagai "
                "GeoPackage atau Shapefile (Export > Save Features As), "
                "lalu jalankan lagi pada layer hasil simpanan."))

        selesai = False
        try:
            layer.beginEditCommand("Contour Label")
            for nama, tipe in ((nama_indeks, "int"), (nama_label, "str")):
                if layer.fields().indexFromName(nama) < 0:
                    if not layer.addAttribute(_field_baru(nama, tipe)):
                        raise QgsProcessingException(_tr(
                            "Gagal menambah field '{}'.").format(nama))
                    feedback.pushInfo(_tr("Field '{}' dibuat.").format(nama))
            layer.updateFields()

            idx_indeks = layer.fields().indexFromName(nama_indeks)
            idx_label = layer.fields().indexFromName(nama_label)
            if idx_indeks < 0 or idx_label < 0:
                raise QgsProcessingException(_tr(
                    "Field indeks/label tidak ditemukan setelah dibuat. "
                    "Untuk Shapefile, nama field maksimal 10 karakter."))
            indeks_numerik = layer.fields().at(idx_indeks).isNumeric()
            label_numerik = layer.fields().at(idx_label).isNumeric()
            if label_numerik and akhiran:
                feedback.pushWarning(_tr(
                    "Field label bertipe angka, akhiran '{}' diabaikan.").format(akhiran))

            # 5. Tulis nilai
            jumlah_mayor = jumlah_minor = 0
            total = max(len(nilai), 1)
            for i, (fid, v) in enumerate(nilai.items()):
                if feedback.isCanceled():
                    raise QgsProcessingException(_tr("Dibatalkan."))
                if v is None:
                    isi_indeks, isi_label = None, None
                elif core.adalah_mayor(v, interval_mayor, offset):
                    jumlah_mayor += 1
                    isi_indeks = 1 if indeks_numerik else "1"
                    isi_label = (core.label_numerik(v) if label_numerik
                                 else core.format_label(v, akhiran))
                else:
                    jumlah_minor += 1
                    isi_indeks = 0 if indeks_numerik else "0"
                    isi_label = None
                layer.changeAttributeValues(fid, {idx_indeks: isi_indeks,
                                                  idx_label: isi_label})
                if i % 200 == 0:
                    feedback.setProgress((50.0 if orientasi else 100.0) * i / total)

            # 6. Orientasi ke atas lereng
            jumlah_dibalik = jumlah_tak_tentu = 0
            if orientasi:
                jumlah_dibalik, jumlah_tak_tentu = self._orientasikan(
                    layer, nilai, dem, context, feedback)
            layer.endEditCommand()
            selesai = True
        finally:
            if not selesai:
                layer.destroyEditCommand()
                if not sedang_edit:
                    layer.rollBack()

        if not sedang_edit:
            if not layer.commitChanges():
                galat = "; ".join(layer.commitErrors())
                layer.rollBack()
                raise QgsProcessingException(_tr("Gagal menyimpan: {}").format(galat))
        else:
            feedback.pushWarning(_tr(
                "Layer sedang dalam mode edit, jadi perubahan belum disimpan. "
                "Tekan Save Layer Edits bila hasilnya sudah sesuai."))

        if jumlah_mayor == 0:
            feedback.pushWarning(_tr(
                "Tidak ada garis yang jatuh pada kelipatan {} m. Periksa "
                "interval atau kelipatan.").format(core.format_label(interval_mayor)))

        # 7. Style
        if self.parameterAsBoolean(parameters, self.TERAPKAN_STYLE, context):
            from . import styling
            styling.terapkan(layer, nama_indeks, nama_label, indeks_numerik,
                             ikuti_arah_garis=orientasi,
                             ada_tanpa_nilai=jumlah_kosong > 0)
            feedback.pushInfo(_tr("Style garis dan label diterapkan."))
        elif orientasi:
            feedback.pushWarning(_tr(
                "Style tidak diterapkan. Agar label menghadap ke atas lereng, "
                "atur Label > Rendering > Upside-down labels menjadi 'Show all'."))

        feedback.pushInfo(_tr("Selesai: {} mayor, {} minor, {} tanpa nilai.").format(
            jumlah_mayor, jumlah_minor, jumlah_kosong))
        feedback.setProgress(100)

        return {
            "OUTPUT": layer.id(),
            "INTERVAL_TERPAKAI": interval,
            "INTERVAL_MAYOR_TERPAKAI": interval_mayor,
            "JUMLAH_MAYOR": jumlah_mayor,
            "JUMLAH_MINOR": jumlah_minor,
            "JUMLAH_KOSONG": jumlah_kosong,
            "JUMLAH_DIBALIK": jumlah_dibalik,
            "JUMLAH_TAK_TENTU": jumlah_tak_tentu,
        }

    # ---- orientasi ------------------------------------------------------
    def _orientasikan(self, layer, nilai, dem, context, feedback):
        from . import orientasi as ori

        fitur = []
        for feat in layer.getFeatures():
            if feedback.isCanceled():
                raise QgsProcessingException(_tr("Dibatalkan."))
            elev = nilai.get(feat.id())
            if elev is None or not feat.hasGeometry():
                continue
            fitur.append((feat.id(), feat.geometry(), elev))

        if dem is not None:
            penilai = ori.PenilaiDEM(dem, layer.crs(), context.transformContext())
        else:
            semua = [(b, elev) for _, g, elev in fitur for b in ori.bagian_garis(g)]
            penilai = ori.PenilaiTetangga(semua)

        # Tahap 1: nilai setiap bagian garis
        total = max(len(fitur), 1)
        skor_fitur = []
        for i, (fid, geom, elev) in enumerate(fitur):
            if feedback.isCanceled():
                raise QgsProcessingException(_tr("Dibatalkan."))
            bagian = ori.bagian_garis(geom)
            skor_fitur.append((fid, geom, bagian, [penilai.skor(b, elev) for b in bagian]))
            if i % 50 == 0:
                feedback.setProgress(50.0 + 45.0 * i / total)

        # Bagian yang tak terpastikan (mis. kontur tunggal) mengikuti pola
        # arah mayoritas data: GDAL Contour, misalnya, mengarahkan semua garis
        # secara seragam, jadi pola itu berlaku juga untuk garis yang ragu.
        semua_skor = [sk for _, _, _, daftar in skor_fitur for sk in daftar]
        perlu_balik = sum(1 for sk in semua_skor if sk < 0)
        sudah_benar = sum(1 for sk in semua_skor if sk > 0)
        terpastikan = perlu_balik + sudah_benar
        bawaan = 0
        if terpastikan >= 10:
            if perlu_balik / terpastikan >= 0.8:
                bawaan = -1
            elif sudah_benar / terpastikan >= 0.8:
                bawaan = 1

        # Tahap 2: balik arah bila perlu
        dibalik = tak_tentu = ikut_pola = 0
        for fid, geom, bagian, daftar in skor_fitur:
            baru, berubah = [], False
            for b, sk in zip(bagian, daftar):
                if sk == 0:
                    if bawaan == 0:
                        tak_tentu += 1
                    else:
                        ikut_pola += 1
                        sk = bawaan
                if sk < 0:
                    baru.append(b.reversed())
                    berubah = True
                else:
                    baru.append(b)
            if berubah:
                layer.changeGeometry(fid, ori.susun_geometri(geom, baru))
                dibalik += 1

        feedback.pushInfo(_tr("Orientasi: {} garis dibalik arahnya.").format(dibalik))
        if ikut_pola:
            feedback.pushInfo(_tr(
                "{} bagian garis tanpa petunjuk lereng (mis. puncak/cekungan "
                "tunggal) mengikuti pola arah mayoritas data.").format(ikut_pola))
        if tak_tentu:
            feedback.pushWarning(_tr(
                "{} bagian garis tidak bisa dipastikan arah lerengnya "
                "(mis. kontur tunggal tanpa tetangga atau di luar DEM); "
                "arahnya dibiarkan.").format(tak_tentu))
        return dibalik, tak_tentu
