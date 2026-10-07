# -*- coding: utf-8 -*-
"""Classe-base comum a todas as ferramentas + utilitários compartilhados."""
from qgis.core import QgsProcessingAlgorithm
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon

from . import ajuda
from .calculos import para_float

GRUPO_VERTICES = ('Vértices virtuais', 'vertices_virtuais')
GRUPO_EIXOS = ('Eixos e linhas paralelas', 'eixos_paralelas')


class VVAlgoritmo(QgsProcessingAlgorithm):
    """Define grupo, ícone, ajuda (HTML com imagens/link) e instanciação."""
    NOME = ''
    TITULO = ''
    RESUMO = ''          # uma linha, texto simples
    DESCRICAO = ''       # HTML do painel de ajuda
    GRUPO = GRUPO_VERTICES

    def tr(self, texto):
        return QCoreApplication.translate('Processing', texto)

    def createInstance(self):
        return type(self)()

    def name(self):
        return self.NOME

    def displayName(self):
        return self.tr(self.TITULO)

    def group(self):
        return self.tr(self.GRUPO[0])

    def groupId(self):
        return self.GRUPO[1]

    def shortDescription(self):
        return self.tr(self.RESUMO)

    def shortHelpString(self):
        return ajuda.montar_ajuda(self.tr(self.TITULO), self.DESCRICAO)

    def helpUrl(self):
        return ajuda.LINK_DOCUMENTACAO

    def icon(self):
        return QIcon(ajuda.caminho_recurso('icon.png'))


def achar_campo_id(fonte):
    """Primeiro campo de texto da camada (ou o primeiro campo). Usado se o ID não for informado."""
    campos = fonte.fields()
    for c in campos:
        if c.typeName().lower() in ('string', 'text', 'varchar', 'qstring'):
            return c.name()
    return campos.at(0).name() if campos.count() > 0 else None


def ler_pontos_base(fonte, campo_id, campo_dpx, campo_dpy):
    """Dicionário {id: {'x','y','dpx','dpy'}} a partir da camada de pontos."""
    pontos = {}
    for feat in fonte.getFeatures():
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            continue
        pt = geom.asMultiPoint()[0] if geom.isMultipart() else geom.asPoint()
        pid = str(feat[campo_id]).strip()
        pontos[pid] = {
            'x': pt.x(), 'y': pt.y(),
            'dpx': para_float(feat[campo_dpx]) if campo_dpx else 0.0,
            'dpy': para_float(feat[campo_dpy]) if campo_dpy else 0.0,
        }
    return pontos
