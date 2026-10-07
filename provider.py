# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from . import ajuda
from .algoritmos.intersecao_angular import IntersecaoAngular
from .algoritmos.intersecao_linear import IntersecaoLinear
from .algoritmos.intersecao_retas import IntersecaoRetas
from .algoritmos.regra_paralelogramo import RegraParalelogramo
from .algoritmos.pontos_para_linha import PontosParaLinha
from .algoritmos.linhas_paralelas import LinhasParalelas


class VerticesVirtuaisProvider(QgsProcessingProvider):

    def loadAlgorithms(self):
        for alg in (IntersecaoAngular, IntersecaoLinear, IntersecaoRetas,
                    RegraParalelogramo, PontosParaLinha, LinhasParalelas):
            self.addAlgorithm(alg())

    def id(self):
        return 'vvtoolbox'

    def name(self):
        return 'Vértices Virtuais Toolbox'

    def longName(self):
        return self.name()

    def icon(self):
        return QIcon(ajuda.caminho_recurso('icon.png'))
