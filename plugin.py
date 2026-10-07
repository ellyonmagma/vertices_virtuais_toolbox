# -*- coding: utf-8 -*-
from qgis.core import QgsApplication
from .provider import VerticesVirtuaisProvider


class VerticesVirtuaisPlugin:
    """Plugin que registra o provedor de algoritmos no Processing."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initProcessing(self):
        self.provider = VerticesVirtuaisProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

    def unload(self):
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
