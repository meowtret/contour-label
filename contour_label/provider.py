# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .algorithm import ContourLabelAlgorithm


class ContourLabelProvider(QgsProcessingProvider):

    def loadAlgorithms(self):
        self.addAlgorithm(ContourLabelAlgorithm())

    def id(self):
        return "contourlabel"

    def name(self):
        return "Contour Label"

    def longName(self):
        return self.name()

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))
