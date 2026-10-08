"""Independent stdlib VECM oracle for the predeclared finite full-rank domain.

Uses twice-reorthogonalized QR regressions, Cholesky whitening and symmetric
Jacobi eigenvectors. No statsmodels, NumPy, SciPy or role-source imports.
The fitted rank-r space is normalized by its first r rows. Calculations are
fresh from the declared input arrays, not saved baseline/reference outputs.
"""
import math
import functools
import gzip
import hashlib
import json
from pathlib import Path


def transpose(a):
    return [list(row) for row in zip(*a)] if a else []


def dot(a, b):
    return math.fsum(x * y for x, y in zip(a, b))


def mm(a, b):
    bt = transpose(b)
    return [[dot(row, col) for col in bt] for row in a]


def cross(a, b):
    at, bt = transpose(a), transpose(b)
    return [[dot(col, other) for other in bt] for col in at]


def identity(n):
    return [[float(i == j) for j in range(n)] for i in range(n)]


def invert(a):
    """Small pivoted elimination; never creates an observation-square matrix."""
    n = len(a)
    work = [list(row) + ident for row, ident in zip(a, identity(n))]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(work[row][col]))
        work[col], work[pivot] = work[pivot], work[col]
        divisor = work[col][col]
        if abs(divisor) < 1e-24:
            raise ValueError("oracle domain requires full-rank regression matrices")
        work[col] = [value / divisor for value in work[col]]
        for row in range(n):
            if row != col:
                factor = work[row][col]
                work[row] = [x - factor * y for x, y in zip(work[row], work[col])]
    return [row[n:] for row in work]


def cholesky(a):
    n = len(a)
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            value = a[i][j] - dot(lower[i][:j], lower[j][:j])
            lower[i][j] = math.sqrt(value) if i == j else value / lower[j][j]
    return lower


def eigensymmetric(a):
    """Jacobi rotations, independent of the project's LAPACK eig path."""
    n = len(a)
    matrix, vectors = [list(row) for row in a], identity(n)
    scale = max(1.0, max(abs(matrix[i][i]) for i in range(n)))
    for _ in range(100 * n * n):
        if n == 1:
            break
        p, q = max(((i, j) for i in range(n) for j in range(i + 1, n)),
                   key=lambda pair: abs(matrix[pair[0]][pair[1]]))
        off = matrix[p][q]
        if abs(off) < 2e-15 * scale:
            break
        tau = (matrix[q][q] - matrix[p][p]) / (2 * off)
        tangent = math.copysign(1 / (abs(tau) + math.sqrt(1 + tau * tau)), tau)
        cosine = 1 / math.sqrt(1 + tangent * tangent)
        sine = tangent * cosine
        pp, qq = matrix[p][p], matrix[q][q]
        matrix[p][p], matrix[q][q] = pp - tangent * off, qq + tangent * off
        matrix[p][q] = matrix[q][p] = 0.0
        for i in range(n):
            if i not in (p, q):
                ip, iq = matrix[i][p], matrix[i][q]
                matrix[i][p] = matrix[p][i] = cosine * ip - sine * iq
                matrix[i][q] = matrix[q][i] = sine * ip + cosine * iq
            vp, vq = vectors[i][p], vectors[i][q]
            vectors[i][p], vectors[i][q] = cosine * vp - sine * vq, sine * vp + cosine * vq
    else:
        raise ValueError("Jacobi oracle did not converge")
    order = sorted(range(n), key=lambda i: matrix[i][i], reverse=True)
    return [matrix[i][i] for i in order], [[row[i] for i in order] for row in vectors]


def qr(design):
    columns = transpose(design)
    q, upper = [], [[0.0] * len(columns) for _ in columns]
    for j, column in enumerate(columns):
        remaining = list(column)
        for _ in range(2):
            for i, basis in enumerate(q):
                amount = dot(basis, remaining)
                upper[i][j] += amount
                remaining = [x - amount * y for x, y in zip(remaining, basis)]
        norm = math.sqrt(dot(remaining, remaining))
        if norm < 1e-12:
            raise ValueError("oracle domain requires independent regressors")
        upper[j][j] = norm
        q.append([value / norm for value in remaining])
    return q, upper


def regression(response, q, upper):
    columns = transpose(response)
    coefficients, residuals = [], []
    for column in columns:
        projected = [dot(basis, column) for basis in q]
        coef = [0.0] * len(q)
        for i in range(len(q) - 1, -1, -1):
            coef[i] = (projected[i] - dot(upper[i][i + 1:], coef[i + 1:])) / upper[i][i]
        coefficients.append(coef)
        residuals.append([value - math.fsum(projected[i] * q[i][t] for i in range(len(q)))
                          for t, value in enumerate(column)])
    return transpose(coefficients), transpose(residuals)


def seasonal(t, periods):
    return [float(t % periods == season) - 1 / periods for season in range(periods - 1)] if periods else []


def flatten(a):
    return [value for row in a for value in row]


def fitted(case, endog, exog=None, exog_coint=None):
    """Compute every declared public statistic from independent input rows."""
    k, rank, lag = len(endog[0]), case["rank"], case["k_ar_diff"]
    det, seasons = case["det"], case["seasons"]
    start, total = lag + 1, len(endog)
    response, levels, short = [], [], []
    for t in range(start, total):
        response.append([endog[t][j] - endog[t - 1][j] for j in range(k)])
        levels.append(list(endog[t - 1]) + ([1.0] if "ci" in det else [])
                      + ([float(t)] if "li" in det else [])
                      + (list(exog_coint[t - 1]) if exog_coint is not None else []))
        short.append([endog[t - offset][j] - endog[t - offset - 1][j]
                      for offset in range(1, lag + 1) for j in range(k)]
                     + ([1.0] if "co" in det else []) + seasonal(t, seasons)
                     + ([float(t + 1)] if "lo" in det else [])
                     + (list(exog[t]) if exog is not None else []))
    n = len(response)
    q, upper = qr(short)
    _, r0 = regression(response, q, upper)
    _, r1 = regression(levels, q, upper)
    s00 = [[v / n for v in row] for row in cross(r0, r0)]
    s01 = [[v / n for v in row] for row in cross(r0, r1)]
    s11 = [[v / n for v in row] for row in cross(r1, r1)]
    whiten = transpose(invert(cholesky(s11)))
    correlation = mm(s01, whiten)
    values, vectors = eigensymmetric(mm(mm(transpose(correlation), invert(s00)), correlation))
    beta = mm(whiten, [row[:rank] for row in vectors])
    beta = mm(beta, invert(beta[:rank]))
    alpha = mm(mm(s01, beta), invert(mm(mm(transpose(beta), s11), beta)))
    equilibrium = mm(levels, beta)
    correction = mm(equilibrium, transpose(alpha))
    adjusted = [[y - value for y, value in zip(row, change)] for row, change in zip(response, correction)]
    gamma_t, error = regression(adjusted, q, upper)
    gamma = transpose(gamma_t) if gamma_t else [[] for _ in range(k)]
    sigma = [[v / n for v in row] for row in cross(error, error)]
    design = [eq + sh for eq, sh in zip(equilibrium, short)]
    inverse_information = invert(cross(design, design))
    stderr_alpha = [[math.sqrt(max(0.0, sigma[i][i] * inverse_information[j][j]))
                     for j in range(rank)] for i in range(k)]
    free_levels = [row[rank:] for row in r1]
    free_inverse = invert(cross(free_levels, free_levels))
    alpha_inverse = invert(mm(mm(transpose(alpha), invert(sigma)), alpha))
    # Preserve the public API's legacy column-major interpretation of the
    # coefficient-variance diagonal, including its rank>1 coordinate layout.
    # This is an output-layout obligation, not a change to the fitted model.
    free_count = len(free_inverse)
    standard_deviations = [math.sqrt(max(0.0, free_inverse[i][i] * alpha_inverse[j][j]))
                          for i in range(free_count) for j in range(rank)]
    stderr_beta = [[0.0] * rank for _ in range(rank)] + [
        [standard_deviations[i + j * free_count] for j in range(rank)] for i in range(k - rank)]
    pvalues = [[math.erfc(abs(gamma[i][j]) / math.sqrt(2 * sigma[i][i] * inverse_information[rank + j][rank + j]))
                for j in range(k * lag)] for i in range(k)]
    lower00 = cholesky(s00)
    logdet00 = 2 * math.fsum(math.log(lower00[i][i]) for i in range(k))
    llf = -k * n * (math.log(2 * math.pi) + 1) / 2 - n * (logdet00 + math.fsum(math.log1p(-v) for v in values[:rank])) / 2
    result = {"alpha": flatten(alpha), "beta": flatten(beta[:k]),
              "gamma": flatten([row[:k * lag] for row in gamma]), "sigma_u": flatten(sigma),
              "llf": [llf], "stderr_alpha": flatten(stderr_alpha), "stderr_beta": flatten(stderr_beta),
              "pvalues_gamma": flatten(pvalues), "det_coef": flatten([row[k * lag:] for row in gamma]),
              "det_coef_coint": flatten(beta[k:])}
    if exog is None:
        history = [list(row) for row in endog]
        forecasts = []
        for horizon in range(24):
            t = total + horizon
            level = history[-1] + ([1.0] if "ci" in det else []) + ([float(t)] if "li" in det else [])
            if exog_coint is not None:
                raise ValueError("forecast requires declared future exogenous cointegration terms")
            diff = [history[-offset][j] - history[-offset - 1][j]
                    for offset in range(1, lag + 1) for j in range(k)]
            outside = ([1.0] if "co" in det else []) + seasonal(t, seasons) + ([float(t + 1)] if "lo" in det else [])
            equilibrium_value = mm([level], beta)[0]
            row = [history[-1][j] + dot(alpha[j], equilibrium_value) + dot(gamma[j], diff + outside) for j in range(k)]
            history.append(row)
            forecasts.append(row)
        result["predict"] = flatten(forecasts)
    return result


@functools.lru_cache(maxsize=1)
def fixture_inputs():
    data = Path(__file__).with_name("fixture-inputs.json.gz").read_bytes()
    assert hashlib.sha256(data).hexdigest() == "ca31048e0e1362f163faa802b5ef1d33e310765050364dbc5c91d32e8f18c839"
    return json.loads(gzip.decompress(data))


@functools.lru_cache(maxsize=16)
def declared_expected(case, size, seed):
    state = fixture_inputs()[case]
    assert state["case"]["T"] == size and state["case"]["seed"] == seed
    return expected(state)


def expected(case, size=None, seed=None):
    if isinstance(case, str):
        return {"fits": declared_expected(case, size, seed)}
    state = case
    definition = state["case"]
    return [fitted(definition, group["endog"], group.get("exog"), group.get("exog_coint")) for group in state["groups"]]


def equivalent(actual, wanted):
    """Declared finite-output tolerance, with tighter likelihood relative error."""
    if not isinstance(actual, dict) or set(actual) != {"fits"} or set(wanted) != {"fits"}:
        return False
    actual, wanted = actual["fits"], wanted["fits"]
    if not isinstance(actual, list) or len(actual) != len(wanted):
        return False
    for got, want in zip(actual, wanted):
        if got.keys() != want.keys():
            return False
        for key, values in want.items():
            other = got[key]
            if len(other) != len(values):
                return False
            relative = 1e-9 if key == "llf" else 1e-7
            absolute = 1e-6 if key == "llf" else 1e-9
            if not all(math.isfinite(x) and math.isclose(x, y, rel_tol=relative, abs_tol=absolute)
                       for x, y in zip(other, values)):
                return False
    return True
