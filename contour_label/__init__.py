# -*- coding: utf-8 -*-


def classFactory(iface):  # noqa: N802 - nama wajib dari QGIS
    from .plugin import ContourLabelPlugin
    return ContourLabelPlugin(iface)
