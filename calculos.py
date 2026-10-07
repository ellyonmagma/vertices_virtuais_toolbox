# -*- coding: utf-8 -*-
"""
Núcleo matemático do plugin (NÃO depende do QGIS, apenas de numpy).

Todas as propagações de incerteza seguem a lei de propagação de variâncias:
    Σ_saida = J · Σ_entrada · Jᵀ
A matriz Jacobiana J é obtida por diferenças finitas centrais, calculadas num
referencial local (coordenadas reduzidas a um ponto de referência) para evitar
perda de precisão com coordenadas UTM grandes. Isso elimina a dependência do
sympy e deixa o cálculo muito mais rápido.
"""
import math
import numpy as np


# --------------------------------------------------------------------------
# Utilitários
# --------------------------------------------------------------------------
def para_float(valor, padrao=0.0):
    """Converte para float tratando NULL/None/texto vazio/NaN."""
    if valor is None:
        return padrao
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return padrao
    return padrao if math.isnan(v) else v


def exigir_float(valor, nome='valor'):
    """Como para_float, mas levanta erro claro se o dado for inválido."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        raise ValueError("Valor inválido/nulo no campo '%s'." % nome)
    if math.isnan(v):
        raise ValueError("Valor inválido/nulo no campo '%s'." % nome)
    return v


def jacobiano(f, x0, passos):
    """Retorna (f(x0), J) com J por diferenças finitas centrais."""
    x0 = np.asarray(x0, dtype=float)
    f0 = np.atleast_1d(np.asarray(f(x0), dtype=float))
    J = np.zeros((f0.size, x0.size))
    for k in range(x0.size):
        h = passos[k]
        xp, xm = x0.copy(), x0.copy()
        xp[k] += h
        xm[k] -= h
        J[:, k] = (np.atleast_1d(f(xp)) - np.atleast_1d(f(xm))) / (2.0 * h)
    return f0, J


# --------------------------------------------------------------------------
# Interseção angular e linear (variáveis: obs1, obs2, XA, XB, YA, YB)
# --------------------------------------------------------------------------
PASSOS_ANGULAR = (1e-7, 1e-7, 1e-4, 1e-4, 1e-4, 1e-4)
PASSOS_LINEAR = (1e-4, 1e-4, 1e-4, 1e-4, 1e-4, 1e-4)


def modelo_angular(v, ref):
    """Saída: [XP_A, YP_A, XP_B, YP_B, gamma(rad)] em coordenadas reduzidas."""
    alfa, beta, xa, xb, ya, yb = [float(t) for t in v]
    xa -= ref[0]; xb -= ref[0]; ya -= ref[1]; yb -= ref[1]
    dab = math.hypot(xa - xb, ya - yb)
    gama = math.pi - alfa - beta
    sg = math.sin(gama)
    dap = dab * math.sin(beta) / sg
    az_ap = math.atan2(xb - xa, yb - ya) - alfa
    xpa = xa + dap * math.sin(az_ap)
    ypa = ya + dap * math.cos(az_ap)
    dbp = dab * math.sin(alfa) / sg
    az_bp = math.atan2(xa - xb, ya - yb) + beta
    xpb = xb + dbp * math.sin(az_bp)
    ypb = yb + dbp * math.cos(az_bp)
    return np.array([xpa, ypa, xpb, ypb, gama])


def modelo_linear(v, ref):
    """Saída: [XP_A, YP_A, XP_B, YP_B, gamma(rad)] em coordenadas reduzidas."""
    dap, dbp, xa, xb, ya, yb = [float(t) for t in v]
    xa -= ref[0]; xb -= ref[0]; ya -= ref[1]; yb -= ref[1]
    dab = math.hypot(xb - xa, yb - ya)
    gama = math.acos((dap**2 + dbp**2 - dab**2) / (2 * dap * dbp))
    theta_a = math.acos((dab**2 + dap**2 - dbp**2) / (2 * dab * dap))
    az_ap = math.atan2(xb - xa, yb - ya) - theta_a
    xpa = xa + dap * math.sin(az_ap)
    ypa = ya + dap * math.cos(az_ap)
    theta_b = math.acos((dab**2 + dbp**2 - dap**2) / (2 * dab * dbp))
    az_bp = math.atan2(xa - xb, ya - yb) + theta_b
    xpb = xb + dbp * math.sin(az_bp)
    ypb = yb + dbp * math.cos(az_bp)
    return np.array([xpa, ypa, xpb, ypb, gama])


def matriz_covariancia(sigmas, cov_a=0.0, cov_b=0.0):
    """Σ 6x6 diagonal; cov_a = cov(XA,YA) e cov_b = cov(XB,YB)."""
    S = np.diag(np.square(np.asarray(sigmas, dtype=float)))
    S[2, 4] = S[4, 2] = cov_a
    S[3, 5] = S[5, 3] = cov_b
    return S


def resolver_intersecao(modelo, passos, v, S):
    """
    Calcula P pelas rotas A e B, propaga as incertezas e escolhe a rota de
    menor (σE + σN). Retorna dicionário com resultado final e gamma (rad).
    """
    v = np.asarray(v, dtype=float)
    ref = (v[2], v[4])  # (XA, YA)
    f0, J = jacobiano(lambda x: modelo(x, ref), v, passos)
    C = J @ S @ J.T
    var = np.clip(np.diag(C), 0.0, None)
    xa_, ya_ = float(f0[0] + ref[0]), float(f0[1] + ref[1])
    xb_, yb_ = float(f0[2] + ref[0]), float(f0[3] + ref[1])
    sa = (math.sqrt(float(var[0])), math.sqrt(float(var[1])))
    sb = (math.sqrt(float(var[2])), math.sqrt(float(var[3])))
    if (sb[0] + sb[1]) < (sa[0] + sa[1]):
        x, y, sx, sy, origem = xb_, yb_, sb[0], sb[1], 'B'
    else:
        x, y, sx, sy, origem = xa_, ya_, sa[0], sa[1], 'A'
    return {'x': x, 'y': y, 'sx': sx, 'sy': sy, 'origem': origem,
            'gamma': float(f0[4]), 'sgamma': math.sqrt(float(var[4]))}


# --------------------------------------------------------------------------
# Interseção de duas retas (4 pontos): variáveis [x1,y1,x2,y2,x3,y3,x4,y4]
# --------------------------------------------------------------------------
PASSOS_RETAS = (1e-4,) * 8


def _modelo_retas(v, ref):
    x1, y1, x2, y2, x3, y3, x4, y4 = [float(t) for t in v]
    x1 -= ref[0]; x2 -= ref[0]; x3 -= ref[0]; x4 -= ref[0]
    y1 -= ref[1]; y2 -= ref[1]; y3 -= ref[1]; y4 -= ref[1]
    d1x, d1y = x2 - x1, y2 - y1
    d2x, d2y = x4 - x3, y4 - y3
    den = d1x * d2y - d1y * d2x
    if abs(den) < 1e-9 * math.hypot(d1x, d1y) * math.hypot(d2x, d2y) or den == 0.0:
        raise ZeroDivisionError("Retas paralelas ou colineares.")
    t = ((x3 - x1) * d2y - (y3 - y1) * d2x) / den
    return np.array([x1 + t * d1x, y1 + t * d1y])


def intersecao_retas(pontos, sig_xy, S_completa=None):
    """
    pontos: [(x1,y1),(x2,y2),(x3,y3),(x4,y4)]  (reta 1 = P1P2, reta 2 = P3P4)
    sig_xy: [(sx1,sy1), ...]  desvios-padrão
    S_completa: Σ 8x8 na ordem [x1,y1,...,x4,y4] (opcional; permite covariâncias)
    Retorna (E, N, Σ 2x2 de [E,N]).
    """
    v = np.array([c for p in pontos for c in p], dtype=float)
    if S_completa is None:
        S_completa = np.diag(np.square(np.array([c for s in sig_xy for c in s], dtype=float)))
    ref = (v[0], v[1])
    f0, J = jacobiano(lambda x: _modelo_retas(x, ref), v, PASSOS_RETAS)
    C = J @ S_completa @ J.T
    return float(f0[0] + ref[0]), float(f0[1] + ref[1]), C


def intersecao_incerteza(pontos, sig_xy):
    """Versão usada nas linhas paralelas: retorna (ponto, σE, σN)."""
    e, n, C = intersecao_retas(pontos, sig_xy)
    return (e, n), math.sqrt(max(C[0, 0], 0.0)), math.sqrt(max(C[1, 1], 0.0))


# --------------------------------------------------------------------------
# Regra do paralelogramo
# --------------------------------------------------------------------------
def paralelogramo(pa, pb, pc, sa, sb, sc, cov_a=0.0, cov_b=0.0, cov_c=0.0):
    """
    P = PC - PA + PB.   pX = (x,y);  sX = (σx,σy);  cov_X = cov(x,y) do ponto.
    Retorna (x, y, σx, σy, σplani).
    """
    x = pc[0] - pa[0] + pb[0]
    y = pc[1] - pa[1] + pb[1]
    # ordem: [XA, YA, XB, YB, XC, YC]
    S = np.zeros((6, 6))
    for i, (s, c) in enumerate(((sa, cov_a), (sb, cov_b), (sc, cov_c))):
        S[2*i, 2*i] = s[0] ** 2
        S[2*i+1, 2*i+1] = s[1] ** 2
        S[2*i, 2*i+1] = S[2*i+1, 2*i] = c
    Jx = np.array([-1.0, 0.0, 1.0, 0.0, 1.0, 0.0])
    Jy = np.array([0.0, -1.0, 0.0, 1.0, 0.0, 1.0])
    vx, vy = float(Jx @ S @ Jx), float(Jy @ S @ Jy)
    return x, y, math.sqrt(vx), math.sqrt(vy), math.sqrt(vx + vy)


# --------------------------------------------------------------------------
# Eixo e linhas paralelas (pontos como tuplas (x, y, sigmaE, sigmaN))
# --------------------------------------------------------------------------
def azimute(x1, y1, x2, y2, se1, se2, sn1, sn2):
    """Azimute (graus 0-360) e σ do azimute (radianos)."""
    dx, dy = x2 - x1, y2 - y1
    den = dx * dx + dy * dy
    az = math.degrees(math.atan2(dx, dy))
    var = (dy * dy * (se1**2 + se2**2) + dx * dx * (sn1**2 + sn2**2)) / (den * den)
    return (az + 360.0) % 360.0, math.sqrt(var)


def novo_ponto(x, y, az_deg, dist, se, sn, s_az):
    """Ponto a 'dist' do ponto (x,y) no azimute az. Retorna (x, y, σx, σy)."""
    a = math.radians(az_deg)
    nx = x + dist * math.sin(a)
    ny = y + dist * math.cos(a)
    sx = math.sqrt(se**2 + (dist * math.cos(a) * s_az) ** 2)
    sy = math.sqrt(sn**2 + (dist * math.sin(a) * s_az) ** 2)
    return nx, ny, sx, sy


def bissetriz(a, b, c, distancia, lado, miter_limit=4.0):
    """Vértice paralelo pela bissetriz. a,b,c = (x,y,σE,σN). lado: -1 esq, +1 dir."""
    az_ant, s_ant = azimute(a[0], a[1], b[0], b[1], a[2], b[2], a[3], b[3])
    az_prox, s_prox = azimute(b[0], b[1], c[0], c[1], b[2], c[2], b[3], c[3])
    delta = (az_prox - az_ant + 180.0) % 360.0 - 180.0
    az_bis = (az_ant + delta / 2.0 + 360.0) % 360.0
    cos_half = max(math.cos(math.radians(delta / 2.0)), 1e-6)
    d_eff = min(distancia / cos_half, distancia * miter_limit)
    s_bis = 0.5 * math.sqrt(s_ant**2 + s_prox**2)
    x, y, sx, sy = novo_ponto(b[0], b[1], (az_bis + lado * 90 + 360) % 360,
                              d_eff, b[2], b[3], s_bis)
    return x, y, sx, sy, delta


def intersecao_lado(a, b, c, distancia, lado):
    """
    Interseção rigorosa das retas paralelas deslocadas (anterior e seguinte)
    do vértice b. Retorna (E, N, σE, σN, delta). Levanta ZeroDivisionError se
    as retas deslocadas forem paralelas.
    """
    az_ant, s_ant = azimute(a[0], a[1], b[0], b[1], a[2], b[2], a[3], b[3])
    az_prox, s_prox = azimute(b[0], b[1], c[0], c[1], b[2], c[2], b[3], c[3])
    delta = (az_prox - az_ant + 180.0) % 360.0 - 180.0
    d_ant = (az_ant + lado * 90) % 360
    d_prox = (az_prox + lado * 90) % 360
    p1 = novo_ponto(a[0], a[1], d_ant, distancia, a[2], a[3], s_ant)
    p2 = novo_ponto(b[0], b[1], d_ant, distancia, b[2], b[3], s_ant)
    p3 = novo_ponto(b[0], b[1], d_prox, distancia, b[2], b[3], s_prox)
    p4 = novo_ponto(c[0], c[1], d_prox, distancia, c[2], c[3], s_prox)
    pts = [(p[0], p[1]) for p in (p1, p2, p3, p4)]
    sig = [(p[2], p[3]) for p in (p1, p2, p3, p4)]
    (e, n), se, sn = intersecao_incerteza(pts, sig)
    return e, n, se, sn, delta


def otimizar_eixo(dados, distancia, limite_erro=1.5, limite_angulo=2.0):
    """
    Remove iterativamente vértices cuja interseção tem σ > limite_erro (m)
    ou cuja deflexão é < limite_angulo (graus). Retorna índices mantidos.
    """
    idx = list(range(len(dados)))
    while len(idx) > 2:
        pior, maior_erro, menor_delta = -1, -1.0, float('inf')
        for k in range(1, len(idx) - 1):
            a, b, c = dados[idx[k - 1]], dados[idx[k]], dados[idx[k + 1]]
            try:
                _, _, se, sn, delta = intersecao_lado(a, b, c, distancia, -1)
                erro = max(se, sn)
            except (ZeroDivisionError, FloatingPointError, ValueError, OverflowError):
                az1, _ = azimute(a[0], a[1], b[0], b[1], a[2], b[2], a[3], b[3])
                az2, _ = azimute(b[0], b[1], c[0], c[1], b[2], c[2], b[3], c[3])
                delta = (az2 - az1 + 180.0) % 360.0 - 180.0
                erro = float('inf')
            ad = abs(delta)
            if erro > limite_erro or ad < limite_angulo:
                if erro == float('inf'):
                    if maior_erro != float('inf') or ad < menor_delta:
                        maior_erro, menor_delta, pior = float('inf'), ad, k
                elif maior_erro != float('inf') and erro > maior_erro:
                    maior_erro, menor_delta, pior = erro, ad, k
        if pior != -1:
            idx.pop(pior)
        else:
            break
    return idx
