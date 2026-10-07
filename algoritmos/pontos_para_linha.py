# -*- coding: utf-8 -*-
from qgis.core import (
    QgsProcessingParameterFeatureSource, QgsProcessingParameterFeatureSink,
    QgsProcessingException, QgsFeature, QgsGeometry, QgsFields,
)
from ..base import VVAlgoritmo, GRUPO_EIXOS
from ..compat import SRC_POINT, WKB_LINESTRING, FAST_INSERT, novo_campo


class PontosParaLinha(VVAlgoritmo):
    NOME = 'pontos_para_linha'
    TITULO = 'Pontos para Linha (Ordenamento Espacial)'
    GRUPO = GRUPO_EIXOS
    RESUMO = 'Gera uma linha contínua ligando os pontos pelo vizinho mais próximo, sem cruzamentos.'
    DESCRICAO = (
        '<p>Gera uma linha contínua a partir de uma camada de pontos, conectando-os '
        'geometricamente para evitar cruzamentos.</p>'
        '<p>O algoritmo encontra os dois pontos mais distantes entre si (as extremidades '
        'prováveis), usa um deles como partida e conecta iterativamente cada ponto ao '
        'vizinho espacial mais próximo.</p>'
        '<p><b>Dica:</b> para usar apenas os pontos selecionados, marque '
        '"Apenas feições selecionadas" na entrada.</p>'
        '<p>A saída é a entrada indispensável da ferramenta <i>Vértices e Linhas Paralelas</i>.</p>')

    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr('Camada de Pontos de Entrada'), [SRC_POINT]))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Linha Gerada')))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))

        pontos = []
        for feat in source.getFeatures():
            g = feat.geometry()
            if g and not g.isEmpty():
                pontos.append(g.asMultiPoint()[0] if g.isMultipart() else g.asPoint())
        n = len(pontos)
        if n < 2:
            raise QgsProcessingException(self.tr('É necessário pelo menos 2 pontos para formar uma linha.'))
        feedback.pushInfo(self.tr('Analisando espacialmente %d pontos...') % n)

        # 1) extremidade: um dos dois pontos mais distantes entre si
        max_d, ini = -1.0, 0
        for i in range(n):
            if feedback.isCanceled():
                return {}
            for j in range(i + 1, n):
                d = pontos[i].sqrDist(pontos[j])
                if d > max_d:
                    max_d, ini = d, i

        # 2) vizinho mais próximo
        livres = pontos.copy()
        atual = livres.pop(ini)
        ordem = [atual]
        passo = 100.0 / n
        while livres:
            if feedback.isCanceled():
                return {}
            k = min(range(len(livres)), key=lambda q: atual.sqrDist(livres[q]))
            atual = livres.pop(k)
            ordem.append(atual)
            feedback.setProgress(int(len(ordem) * passo))

        campos = QgsFields()
        campos.append(novo_campo('id', 'int'))
        campos.append(novo_campo('num_pontos', 'int'))
        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, campos, WKB_LINESTRING, source.sourceCrs())
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        nf = QgsFeature(campos)
        nf.setGeometry(QgsGeometry.fromPolylineXY(ordem))
        nf.setAttribute('id', 1)
        nf.setAttribute('num_pontos', n)
        sink.addFeature(nf, FAST_INSERT)
        feedback.pushInfo(self.tr('Linha ordenada e construída com sucesso.'))
        return {self.OUTPUT: dest_id}
