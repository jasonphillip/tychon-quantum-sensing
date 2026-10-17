"""Small, explicit [[9,1,3]] code-capacity model. No external dependencies."""
import functools

N = 9
MASK = (1 << N) - 1
X_SUPPORTS = ((0, 1), (1, 2, 4, 5), (3, 4, 6, 7), (7, 8))
Z_SUPPORTS = ((0, 1, 3, 4), (2, 5), (3, 6), (4, 5, 7, 8))


def mask(support):
    return sum(1 << q for q in support)


HX = tuple(map(mask, X_SUPPORTS))
HZ = tuple(map(mask, Z_SUPPORTS))
LX = mask((0, 3, 6))
LZ = mask((0, 1, 2))


def parity(value):
    return value.bit_count() & 1


def syndrome(error):
    """bits 0:4 measure Z stabilizers; bits 4:8 measure X stabilizers."""
    x, z = error & MASK, error >> N
    return sum(parity(x & row) << i for i, row in enumerate(HZ)) | sum(
        parity(z & row) << (i + 4) for i, row in enumerate(HX))


def weight(error):
    return ((error & MASK) | (error >> N)).bit_count()


def logical_class(residual):
    """Use only after confirming residual syndrome=0; 0 means stabilizer."""
    return parity((residual & MASK) & LZ) | (parity((residual >> N) & LX) << 1)


def span(generators):
    group = {0}
    for generator in generators:
        group |= {item ^ generator for item in group}
    return group


STABILIZERS = frozenset(span(HX + tuple(row << N for row in HZ)))


def reference_syndrome(error):
    """Independent support-list commutation implementation, no parity masks."""
    paulis = [((error >> q) & 1, (error >> (q + N)) & 1) for q in range(N)]
    bits = [sum(paulis[q][0] for q in support) % 2 for support in Z_SUPPORTS]
    bits += [sum(paulis[q][1] for q in support) % 2 for support in X_SUPPORTS]
    return sum(bit * 2**i for i, bit in enumerate(bits))


@functools.lru_cache(maxsize=1)
def tables():
    """Exact enumeration; tie breaks by lowest binary correction word."""
    joint = [None] * 256
    for error in sorted(range(1 << (2 * N)), key=lambda e: (weight(e), e)):
        s = syndrome(error)
        if joint[s] is None:
            joint[s] = error
    counts = [[[0] * (N + 1) for _ in range(4)] for _ in range(256)]
    representatives = [[None] * 4 for _ in range(256)]
    for error in range(1 << (2 * N)):
        s = syndrome(error)
        c = logical_class(error ^ joint[s])
        w = weight(error)
        counts[s][c][w] += 1
        old = representatives[s][c]
        if old is None or (w, error) < (weight(old), old):
            representatives[s][c] = error
    x_lut, z_lut = [None] * 16, [None] * 16
    for value in sorted(range(1 << N), key=lambda v: (v.bit_count(), v)):
        sx = syndrome(value)
        sz = syndrome(value << N) >> 4
        if x_lut[sx] is None:
            x_lut[sx] = value
        if z_lut[sz] is None:
            z_lut[sz] = value
    separate = [x_lut[s & 15] | (z_lut[s >> 4] << N) for s in range(256)]
    return joint, separate, counts, representatives, x_lut, z_lut


def probability_weights(p):
    return [(p / 3)**w * (1 - p)**(N - w) for w in range(N + 1)]


def maximum_likelihood_lut(p):
    _, _, counts, representatives, _, _ = tables()
    probs = probability_weights(p)
    result = []
    for s in range(256):
        masses = [sum(n * pr for n, pr in zip(row, probs)) for row in counts[s]]
        # Stable tolerance prevents tiny floating sum order errors choosing a tied class.
        best_mass = max(masses)
        choices = [c for c in range(4) if abs(masses[c] - best_mass) <= 1e-14 * best_mass]
        chosen = min(choices, key=lambda c: (weight(representatives[s][c]), representatives[s][c]))
        result.append(representatives[s][chosen])
    return result


def exact_failure(lut, p):
    joint, _, counts, _, _, _ = tables()
    probs = probability_weights(p)
    failure = 0.0
    total = 0.0
    for s in range(256):
        chosen = logical_class(lut[s] ^ joint[s])
        for c in range(4):
            mass = sum(n * pr for n, pr in zip(counts[s][c], probs))
            total += mass
            if c != chosen:
                failure += mass
    return failure, total


def sample_error(rng, p):
    result = 0
    for q in range(N):
        u = rng.random()
        if u < p:
            pauli = rng.randrange(1, 4)  # 1=X, 2=Z, 3=Y, global phase ignored.
            result |= ((pauli & 1) << q) | (((pauli >> 1) & 1) << (q + N))
    return result
