# -*- coding: utf-8 -*-
"""
Painel de ajuda (lado direito da janela de cada ferramenta).

>>> EDITE AQUI: imagens, link da documentação e rodapé <<<
As imagens ficam na pasta  resources/  (substitua os arquivos, mantendo o nome,
ou troque os nomes abaixo).
"""
import os
from qgis.PyQt.QtCore import QUrl

# ======================= CONFIGURAÇÃO DO PAINEL ===========================
IMAGEM_1 = 'imagem_1_ted.png'          # logo/banner superior   (resources/imagem_1.png)
IMAGEM_2 = 'LAGEAMB2.png'          # logo/banner inferior   (resources/imagem_2.png)
LARGURA_IMAGENS = 200              # largura (px) com que as imagens aparecem
LINK_DOCUMENTACAO = 'https://lageamb.ufpr.br/ferramentas-lageamb/'
TEXTO_LINK = 'Acesse a documentação'
RODAPE = ''                        # frase em itálico no fim. Ex.: '"Seu slogan aqui!"'
MOSTRAR_TITULO = False             # se o QGIS já mostrar o título sozinho, ponha False
COR_TITULO = '#444444'
# ==========================================================================

PASTA_RECURSOS = os.path.join(os.path.dirname(__file__), 'resources')


def caminho_recurso(arquivo):
    return os.path.join(PASTA_RECURSOS, arquivo)


def _img(arquivo):
    caminho = caminho_recurso(arquivo)
    if not arquivo or not os.path.isfile(caminho):
        return ''
    url = QUrl.fromLocalFile(caminho).toString()
    return '<p><img src="%s" width="%d"></p>' % (url, LARGURA_IMAGENS)


def montar_ajuda(titulo, descricao_html):
    """Monta o HTML do painel: título, descrição, imagem 1, link, imagem 2, rodapé."""
    h = []
    if MOSTRAR_TITULO:
        h.append('<h2 style="color:%s;">%s</h2>' % (COR_TITULO, titulo))
    h.append(descricao_html)
    h.append(_img(IMAGEM_1))
    if LINK_DOCUMENTACAO:
        h.append('<p><a href="%s"><b>%s</b></a></p>' % (LINK_DOCUMENTACAO, TEXTO_LINK))
    h.append(_img(IMAGEM_2))
    if RODAPE:
        h.append('<p><i style="color:#555555;">%s</i></p>' % RODAPE)
    return ''.join(h)
