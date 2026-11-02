# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtGui import QIcon
try:  # Qt6: QAction pindah ke QtGui
    from qgis.PyQt.QtGui import QAction
except ImportError:  # Qt5
    from qgis.PyQt.QtWidgets import QAction
from qgis.core import Qgis, QgsApplication, QgsVectorLayer, QgsWkbTypes

from .kompat import ambil
from .provider import ContourLabelProvider

ID_ALGORITMA = "contourlabel:isi_label_kontur"
MENU = "&Contour Label"


class ContourLabelPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.action = None

    def initProcessing(self):
        self.provider = ContourLabelProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        ikon = QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))
        self.action = QAction(ikon, "Isi indeks && label kontur", self.iface.mainWindow())
        self.action.setToolTip("Contour Label: isi indeks mayor/minor dan label garis kontur")
        self.action.triggered.connect(self.jalankan)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToVectorMenu(MENU, self.action)

    def unload(self):
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginVectorMenu(MENU, self.action)
            self.action = None
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

    def jalankan(self):
        from qgis import processing

        param = {}
        layer = self.iface.activeLayer()
        tipe_garis = ambil((Qgis, "GeometryType", "Line"),
                           (QgsWkbTypes, "LineGeometry"))
        if isinstance(layer, QgsVectorLayer) and layer.geometryType() == tipe_garis:
            param["INPUT"] = layer.id()
        processing.execAlgorithmDialog(ID_ALGORITMA, param)
