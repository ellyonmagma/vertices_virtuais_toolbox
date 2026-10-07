# -*- coding: utf-8 -*-
from ..base import GRUPO_VERTICES
from ..calculos import modelo_linear, PASSOS_LINEAR
from .intersecao_base import IntersecaoBase


class IntersecaoLinear(IntersecaoBase):
    NOME = 'intersecao_linear'
    TITULO = 'Interseção Linear'
    GRUPO = GRUPO_VERTICES
    RESUMO = 'Calcula o vértice por interseção linear (distâncias AP e BP) com propagação de incertezas.'
    DESCRICAO = (
        '<p>Cálculo de interseção linear vinculando uma <b>Tabela de Observações</b> '
        'a uma <b>Camada de Pontos Base</b>.</p>'
        '<p>A partir das distâncias AP e BP (lei dos cossenos), determina o ponto P pelas '
        'rotas A e B e adota a de menor incerteza (campo <i>origem_calc</i>).</p>'
        '<p>Inclui o ângulo γ (graus) e sua propagação de erro. Distâncias que não '
        'formam triângulo são ignoradas e informadas no log.</p>')
    ROTULO_OBS1, ROTULO_OBS2 = 'Campo Distância APi (m)', 'Campo Distância BPi (m)'
    ROTULO_DP1, ROTULO_DP2 = 'σ Distância APi (m)', 'σ Distância BPi (m)'
    PASSOS = PASSOS_LINEAR

    def modelo(self, v, ref):
        return modelo_linear(v, ref)
