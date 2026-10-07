# -*- coding: utf-8 -*-
from qgis.core import (
    QgsProcessingParameterVectorLayer, QgsProcessingParameterDistance,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterField,
    QgsProcessingParameterBoolean, QgsProcessingParameterNumber,
    QgsProcessingException, QgsFields, QgsFeature, QgsPointXY,
    QgsGeometry, QgsVectorLayer,
)
from ..base import VVAlgoritmo, GRUPO_EIXOS
from ..calculos import (
    exigir_float, azimute, novo_ponto, bissetriz, intersecao_lado, otimizar_eixo,
)
from ..compat import (
    SRC_POINT, SRC_LINE, SRC_POLYGON, WKB_POINT, WKB_LINESTRING,
    FAST_INSERT, FIELD_NUMERIC, FLAG_NO_THREADING, NUM_DOUBLE, novo_campo,
)


class LinhasParalelas(VVAlgoritmo):
    NOME = 'linhas_paralelas'
    TITULO = 'Vértices e Linhas Paralelas'
    GRUPO = GRUPO_EIXOS
    RESUMO = 'Gera vértices e linhas paralelas a um eixo, com propagação de incertezas.'
    DESCRICAO = (
        '<p>A partir de um eixo (linha de referência) e dos pontos levantados sobre ele, '
        'gera os <b>vértices paralelos</b> à esquerda e à direita, a uma distância '
        '(offset) informada, com propagação de incertezas.</p>'
        '<p>Os pontos são filtrados sobre o eixo e ordenados ao longo dele. Opcionalmente o '
        'eixo é otimizado: removem-se vértices cuja interseção rigorosa tem σ acima do '
        'limite ou cuja deflexão é menor que o ângulo mínimo.</p>'
        '<p>Se houver feição selecionada na camada do eixo, ela é usada; caso contrário, '
        'a primeira feição.</p>'
        '<p>Use a saída da ferramenta <i>Pontos para Linha (Ordenamento Espacial)</i> como eixo.</p>')

    PONTOS = 'pontos_p_de_estrada'
    LINHA = 'linha_referencia'
    DISTANCIA = 'largura_do_buffer'
    SIMPLIFICAR = 'simplificar_eixo'
    LIM_ERRO = 'limite_erro'
    LIM_ANGULO = 'limite_angulo'
    C_Z, C_PE, C_PN, C_PZ, C_ID = 'campo_z', 'campo_prec_este', 'campo_prec_norte', 'campo_prec_z', 'campo_id'
    OUT_EIXO_PTS = 'SaidaEixoPontos'
    OUT_EIXO_LINHA = 'SaidaEixoLinha'
    OUT_PTS = 'SaidaPontosDeslocados'
    OUT_BUFFER = 'SaidaBuffer'

    def flags(self):
        return super().flags() | FLAG_NO_THREADING

    def initAlgorithm(self, config=None):
        add = self.addParameter
        add(QgsProcessingParameterVectorLayer(self.PONTOS, self.tr('Camada de Pontos (Levantamento Total)'), [SRC_POINT]))
        add(QgsProcessingParameterVectorLayer(self.LINHA, self.tr('Linha de Referência (Eixo para Filtragem e Ordenação)'), [SRC_LINE]))
        add(QgsProcessingParameterDistance(self.DISTANCIA, self.tr('Distância para deslocamento (Offset)'),
                                           parentParameterName=self.PONTOS, defaultValue=6))
        add(QgsProcessingParameterBoolean(self.SIMPLIFICAR, self.tr('Simplificar/Otimizar eixo (remover colinearidades)?'),
                                          defaultValue=True))
        for chave, rot in ((self.C_Z, 'Campo de Altimetria (Z)'),
                           (self.C_PE, 'Campo de Precisão - Este (X)'),
                           (self.C_PN, 'Campo de Precisão - Norte (Y)'),
                           (self.C_PZ, 'Campo de Precisão - Altimetria (Z)')):
            add(QgsProcessingParameterField(chave, self.tr(rot), parentLayerParameterName=self.PONTOS, type=FIELD_NUMERIC))
        add(QgsProcessingParameterField(self.C_ID, self.tr('Campo de ID/Identificação'),
                                        parentLayerParameterName=self.PONTOS, optional=True))
        add(QgsProcessingParameterNumber(self.LIM_ERRO, self.tr('Otimização: σ máximo da interseção (m)'),
                                         type=NUM_DOUBLE, defaultValue=1.5, minValue=0.0))
        add(QgsProcessingParameterNumber(self.LIM_ANGULO, self.tr('Otimização: deflexão mínima (graus)'),
                                         type=NUM_DOUBLE, defaultValue=2.0, minValue=0.0))
        add(QgsProcessingParameterFeatureSink(self.OUT_EIXO_PTS, self.tr('Vértices do Eixo Utilizados'), type=SRC_POINT))
        add(QgsProcessingParameterFeatureSink(self.OUT_EIXO_LINHA, self.tr('Novo Eixo Otimizado'), type=SRC_LINE))
        add(QgsProcessingParameterFeatureSink(self.OUT_PTS, self.tr('Vértices Paralelos Gerados (Interseção)'), type=SRC_POINT))
        add(QgsProcessingParameterFeatureSink(self.OUT_BUFFER, self.tr('Buffer Gerado (a partir do Eixo Otimizado)'), type=SRC_POLYGON))

    def processAlgorithm(self, parameters, context, feedback):
        from qgis import processing  # import tardio: o plugin Processing já está carregado aqui

        entrada = self.parameterAsVectorLayer(parameters, self.PONTOS, context)
        linha_layer = self.parameterAsVectorLayer(parameters, self.LINHA, context)
        if entrada is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.PONTOS))
        if linha_layer is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.LINHA))
        distancia = self.parameterAsDouble(parameters, self.DISTANCIA, context)
        simplificar = self.parameterAsBool(parameters, self.SIMPLIFICAR, context)
        lim_erro = self.parameterAsDouble(parameters, self.LIM_ERRO, context)
        lim_ang = self.parameterAsDouble(parameters, self.LIM_ANGULO, context)
        c_z = self.parameterAsString(parameters, self.C_Z, context)
        c_pe = self.parameterAsString(parameters, self.C_PE, context)
        c_pn = self.parameterAsString(parameters, self.C_PN, context)
        c_pz = self.parameterAsString(parameters, self.C_PZ, context)
        c_id = self.parameterAsString(parameters, self.C_ID, context)

        if entrada.crs() != linha_layer.crs():
            feedback.pushWarning(self.tr('As camadas têm CRS diferentes; reprojete antes para evitar resultados incorretos.'))

        if linha_layer.selectedFeatureCount() > 0:
            eixo_feat = list(linha_layer.getSelectedFeatures())[0]
        else:
            eixo_feat = next(linha_layer.getFeatures(), None)
        if eixo_feat is None:
            raise QgsProcessingException(self.tr('A camada de linha de referência está vazia.'))
        eixo_geom = eixo_feat.geometry()

        feedback.pushInfo(self.tr('Filtrando pontos que pertencem ao eixo selecionado...'))
        tol = eixo_geom.buffer(0.001, 5)
        filtrados = []
        for feat in entrada.getFeatures():
            if feat.geometry().intersects(tol):
                filtrados.append((eixo_geom.lineLocatePoint(feat.geometry()), feat))
        if not filtrados:
            raise QgsProcessingException(self.tr('Nenhum ponto encontrado sobre a linha selecionada.'))
        filtrados.sort(key=lambda x: x[0])

        features, ultimo = [], None
        for _, feat in filtrados:
            pt = feat.geometry().asPoint()
            if ultimo is None or pt.sqrDist(ultimo) > 1e-8:
                features.append(feat)
                ultimo = pt
        if len(features) < 2:
            raise QgsProcessingException(self.tr('Após remover duplicados, restaram menos de 2 pontos.'))

        def dados_de(feats):
            out = []
            for f in feats:
                p = f.geometry().asPoint()
                out.append((p.x(), p.y(), exigir_float(f[c_pe], c_pe), exigir_float(f[c_pn], c_pn)))
            return out

        dados = dados_de(features)
        if simplificar:
            feedback.pushInfo(self.tr('Otimizando o eixo (σ > %.2f m ou deflexão < %.2f°)...') % (lim_erro, lim_ang))
            mantidos = otimizar_eixo(dados, distancia, lim_erro, lim_ang)
            features = [features[i] for i in mantidos]
            dados = [dados[i] for i in mantidos]
            if len(features) < 2:
                raise QgsProcessingException(self.tr('Após a otimização, restaram menos de 2 pontos.'))
        else:
            feedback.pushInfo(self.tr('Otimização desativada: todos os pontos não duplicados serão mantidos.'))

        # ---------------- eixo otimizado ----------------
        sink_pts_eixo, id_pts_eixo = self.parameterAsSink(
            parameters, self.OUT_EIXO_PTS, context, entrada.fields(), WKB_POINT, entrada.sourceCrs())
        sink_linha, id_linha = self.parameterAsSink(
            parameters, self.OUT_EIXO_LINHA, context, QgsFields(), WKB_LINESTRING, entrada.sourceCrs())
        for feat in features:
            sink_pts_eixo.addFeature(feat, FAST_INSERT)
        feat_linha = QgsFeature()
        feat_linha.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(d[0], d[1]) for d in dados]))
        sink_linha.addFeature(feat_linha, FAST_INSERT)

        # ---------------- vértices paralelos ----------------
        campos = QgsFields()
        for nome, tipo in (('id_orig', 'int'), ('nome', 'string'), ('lado', 'string'), ('tipo', 'string')):
            campos.append(novo_campo(nome, tipo))
        for nome in ('altimetria', 'sigmax_calc', 'sigmay_calc', 'sigmaz', 'sigmax', 'sigmay', 'sigmax_int', 'sigmay_int'):
            campos.append(novo_campo(nome, 'double', 20, 3))
        campos.append(novo_campo('delta_graus', 'double', 20, 4))
        sink_pts, id_pts = self.parameterAsSink(
            parameters, self.OUT_PTS, context, campos, WKB_POINT, entrada.sourceCrs())

        n = len(features)
        for i, feat in enumerate(features):
            if feedback.isCanceled():
                break
            x, y, pe, pn = dados[i]
            val_id = feat[c_id] if c_id else str(feat.id())
            z = exigir_float(feat[c_z], c_z)
            pz = exigir_float(feat[c_pz], c_pz)

            def adiciona(px, py, lado, tipo, sx, sy, s_int_x=None, s_int_y=None, delta=None):
                f = QgsFeature(campos)
                f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(px, py)))
                f.setAttributes([feat.id(), str(val_id), lado, tipo, z, float(sx), float(sy), pz, pe, pn,
                                 None if s_int_x is None else float(s_int_x),
                                 None if s_int_y is None else float(s_int_y),
                                 None if delta is None else float(delta)])
                sink_pts.addFeature(f, FAST_INSERT)

            if i == 0 or i == n - 1:
                if i == 0:
                    az, s_az = azimute(x, y, dados[1][0], dados[1][1], pe, dados[1][2], pn, dados[1][3])
                    tipo = 'Início'
                else:
                    a = dados[i - 1]
                    az, s_az = azimute(a[0], a[1], x, y, a[2], pe, a[3], pn)
                    tipo = 'Fim'
                ex, ey, sxe, sye = novo_ponto(x, y, (az - 90 + 360) % 360, distancia, pe, pn, s_az)
                dx_, dy_, sxd, syd = novo_ponto(x, y, (az + 90) % 360, distancia, pe, pn, s_az)
                adiciona(ex, ey, 'Esquerda', tipo, sxe, sye)
                adiciona(dx_, dy_, 'Direita', tipo, sxd, syd)
            else:
                a, b, c = dados[i - 1], dados[i], dados[i + 1]
                ve = bissetriz(a, b, c, distancia, -1)
                vd = bissetriz(a, b, c, distancia, +1)
                res = {}
                for lado in (-1, +1):
                    try:
                        r = intersecao_lado(a, b, c, distancia, lado)
                        res[lado] = (r[2], r[3])
                    except (ZeroDivisionError, FloatingPointError, ValueError, OverflowError):
                        res[lado] = (None, None)
                        feedback.pushInfo(self.tr(
                            'Aviso: interseção rigorosa mal condicionada/paralela no vértice id %d (delta=%.2f°) — diagnóstico NULL.')
                            % (feat.id(), ve[4]))
                adiciona(ve[0], ve[1], 'Esquerda', 'Vértice', ve[2], ve[3], res[-1][0], res[-1][1], ve[4])
                adiciona(vd[0], vd[1], 'Direita', 'Vértice', vd[2], vd[3], res[+1][0], res[+1][1], vd[4])
            feedback.setProgress(int((i + 1) * 90.0 / n))

        # ---------------- buffer ----------------
        feedback.pushInfo(self.tr('Gerando buffer a partir do eixo otimizado...'))
        temp = QgsVectorLayer('LineString', 'temp_eixo', 'memory')
        temp.setCrs(entrada.crs())
        temp.dataProvider().addFeatures([feat_linha])
        res_buffer = processing.run('native:buffer', {
            'INPUT': temp, 'DISTANCE': distancia, 'SEGMENTS': 5, 'END_CAP_STYLE': 1,
            'JOIN_STYLE': 1, 'MITER_LIMIT': 2, 'DISSOLVE': True,
            'OUTPUT': parameters[self.OUT_BUFFER]},
            context=context, feedback=feedback, is_child_algorithm=True)

        return {self.OUT_EIXO_PTS: id_pts_eixo, self.OUT_EIXO_LINHA: id_linha,
                self.OUT_PTS: id_pts, self.OUT_BUFFER: res_buffer['OUTPUT']}
