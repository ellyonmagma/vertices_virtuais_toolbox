# -*- coding: utf-8 -*-
"""Fluxo comum às interseções angular e linear (observações x pontos base)."""
import math

from qgis.core import (
    QgsProcessingParameterFeatureSource, QgsProcessingParameterFeatureSink,
    QgsProcessingParameterField, QgsProcessingParameterNumber,
    QgsProcessingException, QgsFeature, QgsGeometry, QgsPointXY,
)

from ..base import VVAlgoritmo, achar_campo_id, ler_pontos_base
from ..calculos import exigir_float, matriz_covariancia, resolver_intersecao
from ..compat import SRC_VECTOR, SRC_POINT, WKB_POINT, FAST_INSERT, NUM_DOUBLE, novo_campo


class IntersecaoBase(VVAlgoritmo):
    OBS_INPUT = 'OBS_INPUT'
    PTS_INPUT = 'PTS_INPUT'
    PTS_ID = 'PTS_ID'
    F_PT_A = 'F_PT_A'
    F_PT_B = 'F_PT_B'
    F_OBS1 = 'F_OBS1'
    F_OBS2 = 'F_OBS2'
    DP_OBS1 = 'DP_OBS1'
    DP_OBS2 = 'DP_OBS2'
    PTS_DP_X = 'PTS_DP_X'
    PTS_DP_Y = 'PTS_DP_Y'
    COV_A = 'COV_A'
    COV_B = 'COV_B'
    OUTPUT = 'OUTPUT'

    # definidos nas subclasses
    ROTULO_OBS1 = ROTULO_OBS2 = ''
    ROTULO_DP1 = ROTULO_DP2 = ''
    PASSOS = ()

    def modelo(self, v, ref):
        raise NotImplementedError

    def converter_observacoes(self, o1, o2, s1, s2):
        """Converte para a unidade interna (angular: graus -> radianos)."""
        return o1, o2, s1, s2

    def initAlgorithm(self, config=None):
        add = self.addParameter
        add(QgsProcessingParameterFeatureSource(self.OBS_INPUT, self.tr('Tabela/Camada de Observações'), [SRC_VECTOR]))
        add(QgsProcessingParameterFeatureSource(self.PTS_INPUT, self.tr('Camada de Pontos Base (Geometria)'), [SRC_POINT]))
        add(QgsProcessingParameterField(self.PTS_ID, self.tr('Campo de ID dos pontos base (vazio = 1º campo de texto)'),
                                        parentLayerParameterName=self.PTS_INPUT, optional=True))
        add(QgsProcessingParameterField(self.F_PT_A, self.tr('Coluna ID Ponto A (em Observações)'), None, self.OBS_INPUT))
        add(QgsProcessingParameterField(self.F_PT_B, self.tr('Coluna ID Ponto B (em Observações)'), None, self.OBS_INPUT))
        add(QgsProcessingParameterField(self.F_OBS1, self.tr(self.ROTULO_OBS1), None, self.OBS_INPUT))
        add(QgsProcessingParameterField(self.F_OBS2, self.tr(self.ROTULO_OBS2), None, self.OBS_INPUT))
        add(QgsProcessingParameterField(self.DP_OBS1, self.tr(self.ROTULO_DP1), None, self.OBS_INPUT))
        add(QgsProcessingParameterField(self.DP_OBS2, self.tr(self.ROTULO_DP2), None, self.OBS_INPUT))
        add(QgsProcessingParameterField(self.PTS_DP_X, self.tr('Campo σE (Este) dos pontos base'), None, self.PTS_INPUT))
        add(QgsProcessingParameterField(self.PTS_DP_Y, self.tr('Campo σN (Norte) dos pontos base'), None, self.PTS_INPUT))
        add(QgsProcessingParameterNumber(self.COV_A, self.tr('Covariância E–N do ponto A (opcional)'),
                                         type=NUM_DOUBLE, defaultValue=0.0, optional=True))
        add(QgsProcessingParameterNumber(self.COV_B, self.tr('Covariância E–N do ponto B (opcional)'),
                                         type=NUM_DOUBLE, defaultValue=0.0, optional=True))
        add(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Camada Calculada')))

    def processAlgorithm(self, parameters, context, feedback):
        obs = self.parameterAsSource(parameters, self.OBS_INPUT, context)
        pts = self.parameterAsSource(parameters, self.PTS_INPUT, context)
        if obs is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.OBS_INPUT))
        if pts is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.PTS_INPUT))

        campo_id = self.parameterAsString(parameters, self.PTS_ID, context) or achar_campo_id(pts)
        if not campo_id or pts.fields().lookupField(campo_id) == -1:
            raise QgsProcessingException(self.tr('Campo de ID não encontrado na Camada de Pontos Base.'))

        f_dpx = self.parameterAsString(parameters, self.PTS_DP_X, context)
        f_dpy = self.parameterAsString(parameters, self.PTS_DP_Y, context)
        pontos = ler_pontos_base(pts, campo_id, f_dpx, f_dpy)

        f_a = self.parameterAsString(parameters, self.F_PT_A, context)
        f_b = self.parameterAsString(parameters, self.F_PT_B, context)
        f_o1 = self.parameterAsString(parameters, self.F_OBS1, context)
        f_o2 = self.parameterAsString(parameters, self.F_OBS2, context)
        f_s1 = self.parameterAsString(parameters, self.DP_OBS1, context)
        f_s2 = self.parameterAsString(parameters, self.DP_OBS2, context)
        cov_a = self.parameterAsDouble(parameters, self.COV_A, context)
        cov_b = self.parameterAsDouble(parameters, self.COV_B, context)

        fields = obs.fields()
        n_orig = fields.count()
        extras = []
        if cov_a != 0.0:
            extras.append('cov_A_NE')
        if cov_b != 0.0:
            extras.append('cov_B_NE')
        extras += ['XP_calc', 'YP_calc', 'DP_XP', 'DP_YP', 'gamma_calc', 'DP_gamma']
        for nome in extras:
            if fields.indexOf(nome) == -1:
                fields.append(novo_campo(nome, 'double'))
        if fields.indexOf('origem_calc') == -1:
            fields.append(novo_campo('origem_calc', 'string'))

        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, fields, WKB_POINT, pts.sourceCrs())
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        total = obs.featureCount()
        passo = 100.0 / total if total else 0
        for atual, feature in enumerate(obs.getFeatures()):
            if feedback.isCanceled():
                break
            try:
                ida, idb = str(feature[f_a]).strip(), str(feature[f_b]).strip()
                for pid in (ida, idb):
                    if pid not in pontos:
                        raise ValueError("Ponto '%s' não encontrado na camada de pontos." % pid)
                A, B = pontos[ida], pontos[idb]

                o1, o2, s1, s2 = self.converter_observacoes(
                    exigir_float(feature[f_o1], f_o1), exigir_float(feature[f_o2], f_o2),
                    exigir_float(feature[f_s1], f_s1), exigir_float(feature[f_s2], f_s2))

                v = [o1, o2, A['x'], B['x'], A['y'], B['y']]
                sig = [s1, s2, A['dpx'], B['dpx'], A['dpy'], B['dpy']]
                S = matriz_covariancia(sig, cov_a, cov_b)
                r = resolver_intersecao(self.modelo, self.PASSOS, v, S)

                nf = QgsFeature(fields)
                nf.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(r['x'], r['y'])))
                for i in range(n_orig):
                    nf.setAttribute(i, feature.attribute(i))
                if cov_a != 0.0:
                    nf.setAttribute('cov_A_NE', cov_a)
                if cov_b != 0.0:
                    nf.setAttribute('cov_B_NE', cov_b)
                nf.setAttribute('XP_calc', r['x'])
                nf.setAttribute('YP_calc', r['y'])
                nf.setAttribute('DP_XP', r['sx'])
                nf.setAttribute('DP_YP', r['sy'])
                nf.setAttribute('gamma_calc', math.degrees(r['gamma']))
                nf.setAttribute('DP_gamma', math.degrees(r['sgamma']))
                nf.setAttribute('origem_calc', r['origem'])
                sink.addFeature(nf, FAST_INSERT)
            except Exception as e:  # uma feição problemática não derruba o lote
                feedback.reportError(self.tr('Feição %d ignorada: %s') % (atual + 1, str(e)))
            feedback.setProgress(int((atual + 1) * passo))

        return {self.OUTPUT: dest_id}
