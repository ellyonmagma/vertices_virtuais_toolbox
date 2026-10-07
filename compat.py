# -*- coding: utf-8 -*-
"""
Camada de compatibilidade QGIS 3.x (Qt5) <-> QGIS 4.x (Qt6).
Resolve nomes de enums que mudaram (o acesso "antigo" foi removido no QGIS 4).
"""
from qgis.core import (
    Qgis, QgsProcessing, QgsProcessingAlgorithm, QgsProcessingParameterField,
    QgsProcessingParameterNumber, QgsFeatureSink, QgsWkbTypes, QgsField,
)
from qgis.PyQt.QtCore import QVariant

try:
    from qgis.PyQt.QtCore import QMetaType
except ImportError:  # pragma: no cover
    QMetaType = None


def _primeiro(*getters):
    for g in getters:
        try:
            return g()
        except AttributeError:
            continue
    raise AttributeError("Enum não encontrado nesta versão do QGIS.")


WKB_POINT = _primeiro(lambda: Qgis.WkbType.Point, lambda: QgsWkbTypes.Point)
WKB_LINESTRING = _primeiro(lambda: Qgis.WkbType.LineString, lambda: QgsWkbTypes.LineString)

SRC_VECTOR = _primeiro(lambda: Qgis.ProcessingSourceType.Vector, lambda: QgsProcessing.TypeVector)
SRC_POINT = _primeiro(lambda: Qgis.ProcessingSourceType.VectorPoint, lambda: QgsProcessing.TypeVectorPoint)
SRC_LINE = _primeiro(lambda: Qgis.ProcessingSourceType.VectorLine, lambda: QgsProcessing.TypeVectorLine)
SRC_POLYGON = _primeiro(lambda: Qgis.ProcessingSourceType.VectorPolygon, lambda: QgsProcessing.TypeVectorPolygon)

FIELD_NUMERIC = _primeiro(lambda: Qgis.ProcessingFieldParameterDataType.Numeric,
                          lambda: QgsProcessingParameterField.Numeric)
NUM_DOUBLE = _primeiro(lambda: Qgis.ProcessingNumberParameterType.Double,
                       lambda: QgsProcessingParameterNumber.Double)
FLAG_NO_THREADING = _primeiro(lambda: Qgis.ProcessingAlgorithmFlag.NoThreading,
                              lambda: QgsProcessingAlgorithm.FlagNoThreading)
FAST_INSERT = _primeiro(lambda: QgsFeatureSink.Flag.FastInsert,
                        lambda: QgsFeatureSink.FastInsert)

_NOMES_QMETATYPE = {'double': 'Double', 'int': 'Int', 'string': 'QString'}
_NOMES_QVARIANT = {'double': 'Double', 'int': 'Int', 'string': 'String'}


def _tipo_campo(tipo):
    if QMetaType is not None and Qgis.QGIS_VERSION_INT >= 33800:
        nome = _NOMES_QMETATYPE[tipo]
        try:
            return getattr(QMetaType.Type, nome)
        except AttributeError:
            return getattr(QMetaType, nome)
    return getattr(QVariant, _NOMES_QVARIANT[tipo])


def novo_campo(nome, tipo='double', comprimento=0, precisao=0):
    """Cria QgsField sem depender de QVariant (removido no QGIS 4)."""
    t = _tipo_campo(tipo)
    nome_tipo = {'double': 'double', 'int': 'integer', 'string': 'text'}[tipo]
    return QgsField(nome, t, nome_tipo, comprimento, precisao)
