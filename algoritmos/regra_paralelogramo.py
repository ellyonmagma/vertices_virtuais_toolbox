# -*- coding: utf-8 -*-
from qgis.core import (
    QgsProcessingParameterFeatureSource, QgsProcessingParameterFeatureSink,
    QgsProcessingParameterField, QgsProcessingParameterNumber,
    QgsProcessingException, QgsFeature, QgsGeometry, QgsPointXY,
)
from ..base import VVAlgoritmo, GRUPO_VERTICES, achar_campo_id, ler_pontos_base
from ..calculos import paralelogramo
from ..compat import SRC_VECTOR, SRC_POINT, WKB_POINT, FAST_INSERT, NUM_DOUBLE, novo_campo


class RegraParalelogramo(VVAlgoritmo):
    NOME = 'regra_paralelogramo'
    TITULO = 'Regra do Paralelogramo'
    GRUPO = GRUPO_VERTICES
    RESUMO = 'Determina o vértice virtual a partir de três pontos (PA, PB, PC) pela regra do paralelogramo.'
    DESCRICAO = (
        '<p>Determina as coordenadas do vértice virtual a partir de três pontos '
        '<b>PA</b>, <b>PB</b> e <b>PC</b>:</p>'
        '<p style="margin-left:10px;">X = X<sub>PC</sub> − X<sub>PA</sub> + X<sub>PB</sub><br>'
        'Y = Y<sub>PC</sub> − Y<sub>PA</sub> + Y<sub>PB</sub></p>'
        '<p>Propagação de incertezas (derivadas parciais unitárias):<br>'
        'σ²<sub>X</sub> = σ²<sub>XPA</sub> + σ²<sub>XPB</sub> + σ²<sub>XPC</sub> '
        '(idem para Y). É possível informar a covariância E–N de cada ponto.</p>'
        '<p><b>Tabela de Observações:</b> cada linha define um vértice (IDs de PA, PB e PC).<br>'
        '<b>Camada de Pontos Base:</b> coordenadas e desvios-padrão dos pontos de apoio.</p>')

    OBS_INPUT, PTS_INPUT, PTS_ID = 'OBS_INPUT', 'PTS_INPUT', 'PTS_ID'
    F_PA, F_PB, F_PC = 'F_PA', 'F_PB', 'F_PC'
    PTS_DP_X, PTS_DP_Y = 'PTS_DP_X', 'PTS_DP_Y'
    COV_PA, COV_PB, COV_PC = 'COV_PA', 'COV_PB', 'COV_PC'
    OUTPUT = 'OUTPUT'
    NOMES_COV = ('cov_PA_XY', 'cov_PB_XY', 'cov_PC_XY')

    def initAlgorithm(self, config=None):
        add = self.addParameter
        add(QgsProcessingParameterFeatureSource(self.OBS_INPUT, self.tr('Tabela/Camada de Observações'), [SRC_VECTOR]))
        add(QgsProcessingParameterFeatureSource(self.PTS_INPUT, self.tr('Camada de Pontos Base (Geometria)'), [SRC_POINT]))
        add(QgsProcessingParameterField(self.PTS_ID, self.tr('Campo de ID dos pontos base (vazio = 1º campo de texto)'),
                                        parentLayerParameterName=self.PTS_INPUT, optional=True))
        add(QgsProcessingParameterField(self.F_PA, self.tr('Coluna ID Ponto PA (em Observações)'), None, self.OBS_INPUT))
        add(QgsProcessingParameterField(self.F_PB, self.tr('Coluna ID Ponto PB (em Observações)'), None, self.OBS_INPUT))
        add(QgsProcessingParameterField(self.F_PC, self.tr('Coluna ID Ponto PC (em Observações)'), None, self.OBS_INPUT))
        add(QgsProcessingParameterField(self.PTS_DP_X, self.tr('Campo σE (Este) dos pontos base'), None, self.PTS_INPUT))
        add(QgsProcessingParameterField(self.PTS_DP_Y, self.tr('Campo σN (Norte) dos pontos base'), None, self.PTS_INPUT))
        for chave, rot in ((self.COV_PA, 'PA'), (self.COV_PB, 'PB'), (self.COV_PC, 'PC')):
            add(QgsProcessingParameterNumber(chave, self.tr('Covariância E–N de %s (opcional)') % rot,
                                             type=NUM_DOUBLE, defaultValue=0.0, optional=True))
        add(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Vértice Virtual (Paralelogramo)')))

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
        pontos = ler_pontos_base(pts, campo_id,
                                 self.parameterAsString(parameters, self.PTS_DP_X, context),
                                 self.parameterAsString(parameters, self.PTS_DP_Y, context))

        cov = [self.parameterAsDouble(parameters, k, context) for k in (self.COV_PA, self.COV_PB, self.COV_PC)]
        f_ids = [self.parameterAsString(parameters, k, context) for k in (self.F_PA, self.F_PB, self.F_PC)]

        fields = obs.fields()
        n_orig = fields.count()
        extras = [n for c, n in zip(cov, self.NOMES_COV) if c != 0.0]
        extras += ['XP_calc', 'YP_calc', 'DP_XP', 'DP_YP', 'DP_plani']
        for nome in extras:
            if fields.indexOf(nome) == -1:
                fields.append(novo_campo(nome, 'double'))

        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, fields, WKB_POINT, pts.sourceCrs())
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        total = obs.featureCount()
        passo = 100.0 / total if total else 0
        for atual, feature in enumerate(obs.getFeatures()):
            if feedback.isCanceled():
                break
            try:
                P = []
                for f in f_ids:
                    pid = str(feature[f]).strip()
                    if pid not in pontos:
                        raise ValueError("Ponto '%s' não encontrado na camada de pontos." % pid)
                    P.append(pontos[pid])
                pa, pb, pc = P
                x, y, sx, sy, sp_ = paralelogramo(
                    (pa['x'], pa['y']), (pb['x'], pb['y']), (pc['x'], pc['y']),
                    (pa['dpx'], pa['dpy']), (pb['dpx'], pb['dpy']), (pc['dpx'], pc['dpy']),
                    cov[0], cov[1], cov[2])

                nf = QgsFeature(fields)
                nf.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                for i in range(n_orig):
                    nf.setAttribute(i, feature.attribute(i))
                for c, nome in zip(cov, self.NOMES_COV):
                    if c != 0.0:
                        nf.setAttribute(nome, c)
                nf.setAttribute('XP_calc', x)
                nf.setAttribute('YP_calc', y)
                nf.setAttribute('DP_XP', sx)
                nf.setAttribute('DP_YP', sy)
                nf.setAttribute('DP_plani', sp_)
                sink.addFeature(nf, FAST_INSERT)
            except Exception as e:
                feedback.reportError(self.tr('Feição %d ignorada: %s') % (atual + 1, str(e)))
            feedback.setProgress(int((atual + 1) * passo))

        return {self.OUTPUT: dest_id}
