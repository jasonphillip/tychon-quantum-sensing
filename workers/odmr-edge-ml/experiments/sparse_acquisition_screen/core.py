"""Causal, photon-counted acquisition policies on a shared known-axis model.

Policies receive a calibrated prior and acquired observations only. The private
oracle exposes one selected bin at a time. No measured-data performance is implied.
"""
from dataclasses import dataclass, replace
from time import perf_counter
import numpy as np
from experiments.scalar_information_limit.forward import (
    Point, forward, FREQUENCIES_MHZ, GAMMA_MHZ_UT,
)

FACTOR = 0.9957299574916568
PARAMETERS = ("field_uT", "center_mhz", "width_mhz")
SCALES = np.array([50., .6, 2.])


@dataclass(frozen=True)
class Acquisition:
    photon_rate: float = 5e8
    dwell_seconds: float = .01
    settling_seconds: float = .0003
    primary_actions: int = 24
    recovery_actions: int = 8
    maximum_actions: int = 32
    credible_half_width_uT: float = 2.

    def validate(self):
        vals = (self.photon_rate, self.dwell_seconds, self.settling_seconds,
                self.credible_half_width_uT)
        if not all(np.isfinite(x) for x in vals):
            raise ValueError("nonfinite acquisition setting")
        if min(self.photon_rate, self.dwell_seconds, self.credible_half_width_uT) <= 0:
            raise ValueError("nonpositive acquisition setting")
        if self.settling_seconds < 0:
            raise ValueError("negative settling cost")
        if any(type(x) is not int or x < 0 for x in
               (self.primary_actions, self.recovery_actions, self.maximum_actions)):
            raise ValueError("action budgets must be nonnegative integers")
        if self.primary_actions < 1 or self.maximum_actions < 1:
            raise ValueError("empty primary budget")
        if self.primary_actions + self.recovery_actions > self.maximum_actions:
            raise ValueError("unfunded recovery budget")

    @property
    def exposure_photons(self):
        return self.photon_rate * self.dwell_seconds


@dataclass(frozen=True)
class Observation:
    index: int
    count: int
    exposure_photons: float
    dwell_seconds: float
    settling_seconds: float
    recovered: bool


class AcquisitionOracle:
    """Evaluator-owned truth and RNG; never passed to a policy."""
    def __init__(self, truth, config, seed):
        config.validate()
        self._truth = truth
        self._config = config
        self._rng = np.random.default_rng(seed)
        self._last = None
        self._actions = 0

    def acquire(self, index, *, recovered=False):
        if type(index) is not int or not 0 <= index < len(FREQUENCIES_MHZ):
            raise ValueError("invalid requested frequency")
        if self._actions >= self._config.maximum_actions:
            raise RuntimeError("photon/action budget exhausted")
        # Only deterministic means are rendered; no noisy hidden spectrum exists.
        rate, _ = forward(self._truth, "fixed_amplitude", FACTOR)
        photons = self._config.exposure_photons
        count = int(self._rng.poisson(photons * float(rate[index])))
        settling = self._config.settling_seconds if self._last != index else 0.
        self._last = index
        self._actions += 1
        return Observation(index, count, photons, self._config.dwell_seconds,
                           settling, bool(recovered))


class GridBelief:
    """Same discrete prior, exact Poisson update, and estimator for every policy."""
    def __init__(self, template=None, axes=None):
        self.template = template or Point(bias_uT=250., slope=.02, contrast=.015)
        self.axes = tuple(np.array(a, dtype=float, copy=True) for a in (axes if axes is not None else (
            np.linspace(20., 70., 101), np.linspace(0., .6, 5),
            np.linspace(4., 6., 3))))
        if len(self.axes) != 3:
            raise ValueError("field, center, and linewidth axes required")
        if any(a.ndim != 1 or len(a) < 2 or not np.isfinite(a).all()
               or np.any(np.diff(a) <= 0) for a in self.axes):
            raise ValueError("invalid prior axes")
        if self.axes[0][0] < 20 or self.axes[0][-1] > 70:
            raise ValueError("field prior outside known-axis scope")
        self.states = np.stack(np.meshgrid(*self.axes, indexing="ij"), -1).reshape(-1, 3)
        self.rates = np.stack([self._rate(p) for p in self.states])
        if not np.isfinite(self.rates).all() or np.any(self.rates <= 0):
            raise ValueError("Poisson mean must be finite and positive")
        for array in (*self.axes, self.states, self.rates):
            array.setflags(write=False)
        self.log_weights = np.full(len(self.states), -np.log(len(self.states)))
        self.weights = np.exp(self.log_weights)
        self.observations = []

    def _rate(self, params):
        point = replace(self.template, **dict(zip(PARAMETERS, params)))
        return forward(point, "fixed_amplitude", FACTOR)[0]

    def clone_prior(self):
        # Calibration table is immutable and shared; posterior state is private.
        other = object.__new__(GridBelief)
        other.template, other.axes = self.template, self.axes
        other.states, other.rates = self.states, self.rates
        other.log_weights = np.full(len(self.states), -np.log(len(self.states)))
        other.weights = np.exp(other.log_weights)
        other.observations = []
        return other

    def update(self, observation):
        if not isinstance(observation, Observation):
            raise TypeError("only observed photon counts may update belief")
        if (type(observation.index) is not int
                or not 0 <= observation.index < self.rates.shape[1]
                or type(observation.count) is not int or observation.count < 0
                or not np.isfinite(observation.exposure_photons)
                or observation.exposure_photons <= 0):
            raise ValueError("invalid Poisson observation")
        mu = self.rates[:, observation.index]
        logw = self.log_weights + observation.count * np.log(mu) - observation.exposure_photons * mu
        logw -= np.max(logw)
        weights = np.exp(logw)
        weights /= weights.sum()
        self.weights = weights
        self.log_weights = logw - np.log(np.exp(logw).sum())
        self.observations.append(observation)

    def estimate(self):
        values = self.axes[0]
        marginal = self.weights.reshape(tuple(len(a) for a in self.axes)).sum(axis=(1, 2))
        cdf = np.cumsum(marginal)
        def quantile(q):
            return float(values[min(int(np.searchsorted(cdf, q)), len(values)-1)])
        return {"estimate_uT": quantile(.5), "lower_uT": quantile(.025),
                "upper_uT": quantile(.975),
                "mean_uT": float(self.weights @ self.states[:, 0]),
                "boundary_mass": float(marginal[0] + marginal[-1])}

    def utility_cost(self, config, last):
        cost = np.full(self.rates.shape[1], config.dwell_seconds + config.settling_seconds)
        if last is not None:
            cost[last] = config.dwell_seconds
        return cost


class UniformPolicy:
    name = "uniform"

    def __init__(self, bins=100):
        # Spread early samples across the domain; every 100 actions visits each bin.
        self.order = sorted(range(bins), key=lambda k: int(f"{k:07b}"[::-1], 2))

    def choose(self, belief, config, history):
        return int(self.order[len(history) % len(self.order)])


class CoarseToFinePolicy:
    name = "coarse_to_fine"

    def choose(self, belief, config, history):
        pilot = np.linspace(0, len(FREQUENCIES_MHZ)-1, 11).round().astype(int)
        if len(history) < len(pilot):
            return int(pilot[len(history)])
        field, center, width = belief.weights @ belief.states
        raw_center = 2871. - .0742 * (belief.template.temperature_K - 300.) + center
        separation = GAMMA_MHZ_UT * (field + belief.template.bias_uT)
        targets = [raw_center + sign*separation + side*width/np.sqrt(12.)
                   for sign in (-1, 1) for side in (-1, 1)]
        target = targets[(len(history)-len(pilot)) % len(targets)]
        return int(np.argmin(abs(FREQUENCIES_MHZ-target)))


class FisherPolicy:
    name = "nuisance_fisher"

    def choose(self, belief, config, history):
        mean = belief.weights @ belief.states
        z = (belief.states-mean)/SCALES
        covariance = (z.T * belief.weights) @ z + np.eye(3)*1e-8
        derivatives = []
        for j, step in enumerate((.01, .0001, .001)):
            plus, minus = mean.copy(), mean.copy()
            plus[j] += step
            minus[j] -= step
            derivatives.append((belief._rate(plus)-belief._rate(minus))/(2*step)*SCALES[j])
        gradient = np.stack(derivatives).T
        mu = belief._rate(mean)
        cg = gradient @ covariance
        # Rank-one expected Poisson Fisher covariance update, including nuisance.
        gain = config.exposure_photons * cg[:, 0]**2 / (
            mu + config.exposure_photons*np.sum(gradient*cg, axis=1))
        last = history[-1].index if history else None
        return int(np.argmax(gain/belief.utility_cost(config, last)))


class BayesianPolicy:
    """Expected posterior field variance, deterministic predictive quadrature.

    Posterior likelihood is exact Poisson. Design integrates an approximation:
    equal-weight posterior quantiles and rounded Gaussian-Poisson outcomes.
    Quadrature convergence must pass before this is a qualified strong baseline.
    """
    name = "bayesian_variance"

    def __init__(self, predictive_states=16, quadrature_nodes=5):
        if predictive_states < 2 or quadrature_nodes < 3:
            raise ValueError("inadequate predictive quadrature")
        self.predictive_states = predictive_states
        nodes, weights = np.polynomial.hermite.hermgauss(quadrature_nodes)
        self.nodes = np.sqrt(2.)*nodes
        self.node_weights = weights/np.sqrt(np.pi)

    def design(self, belief, config, history):
        """Return raw design evidence for preregistered qualification."""
        exposure = config.exposure_photons
        if exposure * float(belief.rates.min()) < 1e4:
            raise ValueError("predictive quadrature only registered for high-count regime")
        # Lexicographic quantiles are deterministic; refinement sensitivity is required.
        cdf = np.cumsum(belief.weights)
        q = (np.arange(self.predictive_states)+.5)/self.predictive_states
        representatives = np.minimum(np.searchsorted(cdf, q), len(cdf)-1)
        field = belief.states[:, 0]
        variance = float(belief.weights @ field**2 - (belief.weights @ field)**2)
        expected = np.zeros(belief.rates.shape[1])
        for i in range(belief.rates.shape[1]):
            rates = belief.rates[:, i]
            lam = exposure * rates[representatives]
            counts = np.maximum(0., np.rint(lam[:, None] + np.sqrt(lam[:, None])*self.nodes))
            for j, node_weight in enumerate(self.node_weights):
                logw = (belief.log_weights[None, :] + counts[:, j, None]*np.log(rates)
                        - exposure*rates)
                logw -= logw.max(axis=1, keepdims=True)
                posterior = np.exp(logw)
                posterior /= posterior.sum(axis=1, keepdims=True)
                v = posterior @ field**2 - (posterior @ field)**2
                expected[i] += node_weight * float(v.mean())
        last = history[-1].index if history else None
        gain = np.maximum(variance-expected, 0.)
        return {"expected_variance_uT2":expected,
                "utility_uT2_per_second":gain/belief.utility_cost(config, last)}

    def utilities(self, belief, config, history):
        return self.design(belief, config, history)["utility_uT2_per_second"]

    def choose(self, belief, config, history):
        return int(np.argmax(self.utilities(belief, config, history)))


def simulate_episode(truth, seed, policy, prior, config):
    """Only this evaluator sees truth; the policy sees model state and history."""
    config.validate()
    if truth.theta != 0 or truth.phi != 0 or truth.bias_uT != 250.:
        raise ValueError("screen is positive known-axis with fixed 250 uT bias only")
    before = perf_counter()
    belief = prior.clone_prior()
    recovery = UniformPolicy()
    episode_setup_seconds = perf_counter()-before
    oracle = AcquisitionOracle(truth, config, seed)
    history, trace = [], []
    policy_time = update_time = 0.
    certified = False
    for step in range(config.primary_actions + config.recovery_actions):
        recovered = step >= config.primary_actions
        before = perf_counter()
        chosen_policy = recovery if recovered else policy
        index = chosen_policy.choose(belief, config, tuple(history))
        decision_seconds = perf_counter()-before
        observation = oracle.acquire(index, recovered=recovered)
        before = perf_counter()
        belief.update(observation)
        estimate = belief.estimate()
        update_seconds = perf_counter()-before
        history.append(observation)
        # This is an internal stopping criterion, not a calibrated confidence guarantee.
        certified = ((estimate["upper_uT"]-estimate["lower_uT"])/2
                     <= config.credible_half_width_uT)
        policy_time += decision_seconds
        update_time += update_seconds
        trace.append({**observation.__dict__, "decision_seconds": decision_seconds,
                      "update_seconds": update_seconds, **estimate,
                      "internal_precision_stop": bool(certified)})
        if certified:
            break
    result = estimate.copy()
    result.update(policy=policy.name, internal_precision_stop=bool(certified),
        failed_precision=not bool(certified), actions=len(history),
        recovery_actions=sum(x.recovered for x in history),
        dwell_seconds=sum(x.dwell_seconds for x in history),
        settling_seconds=sum(x.settling_seconds for x in history),
        normalized_exposure_photons=sum(x.exposure_photons for x in history),
        detected_photons=sum(x.count for x in history),
        decision_seconds=policy_time, update_seconds=update_time,
        episode_setup_seconds=episode_setup_seconds, trace=trace)
    result["modeled_total_seconds"] = (result["dwell_seconds"]+result["settling_seconds"]
        +policy_time+update_time+episode_setup_seconds)
    return result
