# -*- coding: utf-8 -*-
import math
import numpy as np

from qgis.core import (
    QgsProcessingParameterVectorLayer, QgsProcessingParameterField,
    QgsProcessingParameterBoolean, QgsProcessingParameterEnum,
    QgsProcessingParameterString, QgsProcessingParameterFeatureSink,
    QgsProcessingOutputString, QgsProcessingException,
    QgsFeature, QgsGeometry, QgsPointXY, QgsFields,
)
from ..base import VVAlgoritmo, GRUPO_VERTICES
from ..calculos import intersecao_retas, exigir_float
from ..compat import (SRC_POINT, WKB_POINT, FAST_INSERT, FIELD_NUMERIC,
                      FLAG_NO_THREADING, novo_campo)


class IntersecaoRetas(VVAlgoritmo):
    NOME = 'intersecao_retas'
    TITULO = 'Interseção de Retas'
    GRUPO = GRUPO_VERTICES
    RESUMO = 'Interseção de duas retas (4 pontos) com propagação de incertezas planimétricas e altimétrica.'
    DESCRICAO = (
        '<p>Calcula a interseção entre a <b>Reta 1</b> (P1–P2) e a <b>Reta 2</b> (P3–P4) com '
        'propagação de incertezas (σE, σN e covariância E–N) e determinação da altitude.</p>'
        '<p>Informe, pelo <b>ID</b>, os quatro pontos da camada. O campo de identificação '
        '(padrão: <i>nome</i>) deve existir na camada.</p>'
        '<p><b>Covariâncias:</b> quatro valores separados por vírgula, na ordem P1, P2, P3, P4.</p>'
        '<p><b>Método altimétrico:</b> vizinho mais próximo, interpolação ou IDW.</p>'
        '<p>Se marcada a opção de salvar, o ponto calculado é adicionado à própria camada '
        '(com a coluna <i>COV_EN</i>), podendo ser usado como ponto base em novos cálculos.</p>')

    INPUT_LAYER = 'INPUT_LAYER'
    ID_FIELD = 'ID_FIELD'
    LINE1_P1_ID, LINE1_P2_ID = 'LINE1_P1_ID', 'LINE1_P2_ID'
    LINE2_P1_ID, LINE2_P2_ID = 'LINE2_P1_ID', 'LINE2_P2_ID'
    ALTIMETRY_FIELD = 'ALTIMETRY_FIELD'
    DE_FIELD, DN_FIELD, DU_FIELD = 'DE_FIELD', 'DN_FIELD', 'DU_FIELD'
    COV_INPUT = 'COV_INPUT'
    TP_ALT = 'TP_ALT'
    STORE_RESULTS = 'STORE_RESULTS'
    OUTPUT = 'OUTPUT'
    OUTPUT_REPORT = 'OUTPUT_REPORT'
    COV_FIELD_NAME = 'COV_EN'

    def flags(self):
        # edita a camada de entrada -> precisa rodar na thread principal
        return super().flags() | FLAG_NO_THREADING

    def initAlgorithm(self, config=None):
        add = self.addParameter
        add(QgsProcessingParameterVectorLayer(self.INPUT_LAYER, self.tr('Camada de Pontos'), [SRC_POINT]))
        add(QgsProcessingParameterField(self.ID_FIELD, self.tr('Campo de ID dos pontos'),
                                        defaultValue='nome', parentLayerParameterName=self.INPUT_LAYER))
        add(QgsProcessingParameterString(self.LINE1_P1_ID, self.tr('Reta 1: ID do Ponto Inicial (P1)')))
        add(QgsProcessingParameterString(self.LINE1_P2_ID, self.tr('Reta 1: ID do Ponto Final (P2)')))
        add(QgsProcessingParameterString(self.LINE2_P1_ID, self.tr('Reta 2: ID do Ponto Inicial (P3)')))
        add(QgsProcessingParameterString(self.LINE2_P2_ID, self.tr('Reta 2: ID do Ponto Final (P4)')))
        for chave, rot in ((self.ALTIMETRY_FIELD, 'Campo Z (Altitude)'),
                           (self.DE_FIELD, 'Campo DP Este (σE)'),
                           (self.DN_FIELD, 'Campo DP Norte (σN)'),
                           (self.DU_FIELD, 'Campo DP Altitude (σZ)')):
            add(QgsProcessingParameterField(chave, self.tr(rot), parentLayerParameterName=self.INPUT_LAYER,
                                            type=FIELD_NUMERIC))
        add(QgsProcessingParameterString(self.COV_INPUT, self.tr('Covariâncias E–N (P1, P2, P3, P4)'),
                                         defaultValue='0,0,0,0'))
        add(QgsProcessingParameterEnum(self.TP_ALT, self.tr('Método Altimétrico'),
                                       options=['Vizinho mais próximo', 'Interpolação', 'IDW'], defaultValue=0))
        add(QgsProcessingParameterBoolean(self.STORE_RESULTS,
                                          self.tr('Adicionar o ponto calculado à camada de entrada (cria coluna COV_EN)'),
                                          defaultValue=True))
        add(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Ponto de Interseção'),
                                              optional=True, createByDefault=False))
        self.addOutput(QgsProcessingOutputString(self.OUTPUT_REPORT, self.tr('Relatório Final')))

    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsVectorLayer(parameters, self.INPUT_LAYER, context)
        if layer is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT_LAYER))
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context)
        if layer.fields().lookupField(id_field) == -1:
            raise QgsProcessingException(self.tr("A camada não possui o campo de ID '%s'.") % id_field)

        alt_f = self.parameterAsString(parameters, self.ALTIMETRY_FIELD, context)
        de_f = self.parameterAsString(parameters, self.DE_FIELD, context)
        dn_f = self.parameterAsString(parameters, self.DN_FIELD, context)
        du_f = self.parameterAsString(parameters, self.DU_FIELD, context)
        opc = self.parameterAsInt(parameters, self.TP_ALT, context)

        try:
            cov_list = [float(x.strip()) for x in self.parameterAsString(parameters, self.COV_INPUT, context).split(',')]
            if len(cov_list) != 4:
                raise ValueError
        except Exception:
            feedback.reportError(self.tr('Entrada de covariância inválida (use 4 valores separados por vírgula). Usando zeros.'))
            cov_list = [0.0, 0.0, 0.0, 0.0]

        pt_ids = [self.parameterAsString(parameters, k, context).strip() for k in
                  (self.LINE1_P1_ID, self.LINE1_P2_ID, self.LINE2_P1_ID, self.LINE2_P2_ID)]
        if '' in pt_ids:
            raise QgsProcessingException(self.tr('Informe o ID dos quatro pontos.'))

        f_map = {}
        for f in layer.getFeatures():
            pid = str(f[id_field]).strip()
            if pid in pt_ids:
                f_map[pid] = f
        faltando = [p for p in set(pt_ids) if p not in f_map]
        if faltando:
            raise QgsProcessingException(self.tr("Ponto(s) não encontrado(s) no campo '%s': %s") % (id_field, ', '.join(faltando)))
        p_feats = [f_map[p] for p in pt_ids]

        # ---------- dados e matriz de covariância (ordem [x1,y1,...,x4,y4]) ----------
        pts_xy, sig_xy, Zs, dZs = [], [], [], []
        for f, nome in zip(p_feats, pt_ids):
            p = f.geometry().asPoint()
            pts_xy.append((p.x(), p.y()))
            sig_xy.append((exigir_float(f[de_f], de_f), exigir_float(f[dn_f], dn_f)))
            Zs.append(exigir_float(f[alt_f], alt_f))
            dZs.append(exigir_float(f[du_f], du_f))
        S = np.zeros((8, 8))
        for i in range(4):
            S[2*i, 2*i] = sig_xy[i][0] ** 2        # σE²
            S[2*i+1, 2*i+1] = sig_xy[i][1] ** 2    # σN²
            S[2*i, 2*i+1] = S[2*i+1, 2*i] = cov_list[i]

        try:
            E_int, N_int, Cov = intersecao_retas(pts_xy, sig_xy, S)
        except ZeroDivisionError:
            raise QgsProcessingException(self.tr('As retas são paralelas ou colineares.'))
        sE, sN = math.sqrt(max(Cov[0, 0], 0.0)), math.sqrt(max(Cov[1, 1], 0.0))
        cEN = float(Cov[0, 1])

        # ---------- altimetria ----------
        dists = [math.hypot(E_int - x, N_int - y) for x, y in pts_xy]
        idx_v = dists.index(min(dists))
        if opc == 0:
            Z_calc, DZ_calc = Zs[idx_v], dZs[idx_v]
        elif opc == 1:
            a, b = (0, 1) if idx_v < 2 else (2, 3)
            (xa, ya), (xb, yb) = pts_xy[a], pts_xy[b]
            comp2 = (xb - xa) ** 2 + (yb - ya) ** 2
            u = ((E_int - xa) * (xb - xa) + (N_int - ya) * (yb - ya)) / comp2
            Z_calc = Zs[a] + u * (Zs[b] - Zs[a])
            DZ_calc = dZs[idx_v]
        else:
            w = [1 / d if d > 1e-9 else 1e9 for d in dists]
            sw = sum(w)
            Z_calc = sum(z * wi for z, wi in zip(Zs, w)) / sw
            DZ_calc = math.sqrt(sum((wi / sw) ** 2 * dz ** 2 for wi, dz in zip(w, dZs)))

        nome_novo = 'Int_%s_%s' % (pt_ids[0], pt_ids[2])

        # ---------- saída opcional (camada nova) ----------
        campos = QgsFields()
        campos.append(novo_campo('nome', 'string'))
        for n in ('XP_calc', 'YP_calc', 'ZP_calc', 'DP_XP', 'DP_YP', 'DP_ZP', 'cov_EN'):
            campos.append(novo_campo(n, 'double'))
        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, campos, WKB_POINT, layer.crs())
        if sink is not None:
            nf = QgsFeature(campos)
            nf.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(E_int, N_int)))
            nf.setAttributes([nome_novo, E_int, N_int, Z_calc, sE, sN, DZ_calc, cEN])
            sink.addFeature(nf, FAST_INSERT)

        # ---------- grava na camada de entrada (opcional) ----------
        if self.parameterAsBool(parameters, self.STORE_RESULTS, context):
            ja_editando = layer.isEditable()
            if not ja_editando:
                layer.startEditing()
            if layer.fields().lookupField(self.COV_FIELD_NAME) == -1:
                layer.addAttribute(novo_campo(self.COV_FIELD_NAME, 'double'))
                layer.updateFields()
                feedback.pushInfo(self.tr("Coluna '%s' adicionada à camada.") % self.COV_FIELD_NAME)
            nf = QgsFeature(layer.fields())
            nf.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(E_int, N_int)))
            nf[id_field] = nome_novo
            nf[alt_f], nf[de_f], nf[dn_f], nf[du_f] = Z_calc, sE, sN, DZ_calc
            nf[self.COV_FIELD_NAME] = cEN
            layer.addFeature(nf)
            if not ja_editando and not layer.commitChanges():
                raise QgsProcessingException(self.tr('Falha ao salvar na camada: ') + '; '.join(layer.commitErrors()))

        report = ("RESULTADOS DA INTERSEÇÃO (%s):\n"
                  "E: %.4f ± %.4f m\nN: %.4f ± %.4f m\nZ: %.4f ± %.4f m\n"
                  "CovEN resultante: %.8f") % (nome_novo, E_int, sE, N_int, sN, Z_calc, DZ_calc, cEN)
        feedback.pushInfo(report)
        res = {self.OUTPUT_REPORT: report}
        if sink is not None:
            res[self.OUTPUT] = dest_id
        return res
