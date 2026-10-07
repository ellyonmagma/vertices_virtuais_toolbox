# -*- coding: utf-8 -*-
import math
from ..base import GRUPO_VERTICES
from ..calculos import modelo_angular, PASSOS_ANGULAR
from .intersecao_base import IntersecaoBase


class IntersecaoAngular(IntersecaoBase):
    NOME = 'intersecao_angular'
    TITULO = 'Interseção Angular'
    GRUPO = GRUPO_VERTICES
    RESUMO = 'Calcula o vértice por interseção angular (α, β) com propagação de incertezas.'
    DESCRICAO = (
        '<p>Cálculo de interseção angular vinculando uma <b>Tabela de Observações</b> '
        'a uma <b>Camada de Pontos Base</b>.</p>'
        '<p>A partir dos ângulos α e β (em graus) medidos nos pontos A e B, determina o '
        'ponto P pelas rotas A e B e adota a de menor incerteza (campo <i>origem_calc</i>).</p>'
        '<p>Inclui o ângulo γ (graus) e sua propagação de erro.</p>')
    ROTULO_OBS1, ROTULO_OBS2 = 'Campo Alpha (graus)', 'Campo Beta (graus)'
    ROTULO_DP1, ROTULO_DP2 = 'σ Alpha (graus)', 'σ Beta (graus)'
    PASSOS = PASSOS_ANGULAR

    def modelo(self, v, ref):
        return modelo_angular(v, ref)

    def converter_observacoes(self, o1, o2, s1, s2):
        return math.radians(o1), math.radians(o2), math.radians(s1), math.radians(s2)
