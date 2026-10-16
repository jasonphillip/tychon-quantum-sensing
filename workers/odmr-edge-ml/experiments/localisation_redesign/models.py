"""Finite classical grid and a paired physical-loss/control experiment."""
import numpy as np
from scipy import linalg, optimize
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist


class Scaling:
    def fit(self, x, y):
        z = np.log(x)
        self.x_mean, self.x_scale = z.mean(0), np.maximum(z.std(0), 1e-12)
        self.y_mean, self.y_scale = y.mean(0), np.maximum(y.std(0), 1e-12)
        return self

    def x(self, values):
        return (np.log(values) - self.x_mean) / self.x_scale

    def y(self, values):
        return (values - self.y_mean) / self.y_scale

    def inverse(self, values):
        return values * self.y_scale + self.y_mean

    def saved(self):
        return {k: getattr(self, k) for k in ("x_mean", "x_scale", "y_mean", "y_scale")}


def representation(x, weight):
    if weight == 0:
        return x[:, ::3]
    weights = np.tile([1.0, weight, weight], 8)
    return x * weights


def ard_kernel(x, q, theta, family, derivatives=False):
    d = x.shape[1]
    lengths, amplitude = np.exp(theta[:d]), np.exp(2 * theta[d])
    delta = (x[:, None, :] - q[None, :, :]) / lengths
    squared = delta * delta
    radius2 = squared.sum(2)
    if family == "se":
        kernel = amplitude * np.exp(-0.5 * radius2)
        length_gradients = kernel[:, :, None] * squared if derivatives else None
    elif family == "matern32":
        radius = np.sqrt(3 * radius2)
        exponential = amplitude * np.exp(-radius)
        kernel = (1 + radius) * exponential
        length_gradients = 3 * exponential[:, :, None] * squared if derivatives else None
    else:
        raise ValueError("unknown ARD kernel")
    return (kernel, length_gradients) if derivatives else kernel


def gp_objective(theta, x, y, family):
    kernel, gradients = ard_kernel(x, x, theta, family, derivatives=True)
    signal = kernel.copy()
    noise2 = np.exp(2 * theta[-1])
    kernel.flat[::len(x) + 1] += noise2 + 1e-8
    factor = linalg.cho_factor(kernel, lower=True, check_finite=True)
    alpha = linalg.cho_solve(factor, y)
    value = 0.5 * (y @ alpha) + np.log(np.diag(factor[0])).sum() + 0.5 * len(x) * np.log(2 * np.pi)
    derivative = linalg.cho_solve(factor, np.eye(len(x))) - np.outer(alpha, alpha)
    gradient = np.r_[0.5 * np.einsum("ij,ijk->k", derivative, gradients),
                     np.sum(derivative * signal), noise2 * np.trace(derivative)]
    return float(value), gradient


def fit_ard(x, y, family):
    d = x.shape[1]
    all_theta, all_alpha, records = [], [], []
    for axis in range(2):
        choices = []
        for length, noise in ((0.5, 0.01), (2.0, 0.1)):
            theta0 = np.log(np.r_[np.full(d, np.sqrt(d) * length), 1.0, noise])
            bounds = [(np.log(0.05), np.log(100.0))] * d + [(np.log(0.05), np.log(10.0)), (np.log(1e-5), 0.0)]
            result = optimize.minimize(gp_objective, theta0, args=(x, y[:, axis], family), jac=True,
                                       method="L-BFGS-B", bounds=bounds,
                                       options={"maxiter": 60, "maxfun": 500, "maxls": 20, "ftol": 1e-9, "gtol": 1e-5})
            if not np.isfinite(result.fun) or not np.isfinite(result.x).all():
                raise ValueError("ARD optimizer returned nonfinite state")
            choices.append(result)
            records.append({"axis": axis, "start_length_multiplier": length, "start_noise": noise,
                            "negative_log_marginal_likelihood": float(result.fun),
                            "converged": bool(result.success), "status": int(result.status),
                            "message": str(result.message), "iterations": int(result.nit), "evaluations": int(result.nfev)})
        winner = min(range(2), key=lambda i: (choices[i].fun, i))
        theta = choices[winner].x
        kernel = ard_kernel(x, x, theta, family)
        kernel.flat[::len(x) + 1] += np.exp(2 * theta[-1]) + 1e-8
        all_theta.append(theta)
        all_alpha.append(linalg.cho_solve(linalg.cho_factor(kernel, lower=True), y[:, axis]))
        records[axis * 2 + winner]["selected_by_training_likelihood"] = True
    return {"theta": np.stack(all_theta), "alpha": np.column_stack(all_alpha)}, records


def fit_classical(config, x, y):
    name = config["family"]
    xx = representation(x, config.get("quality_weight", 1.0))
    state, information = {}, {}
    if name == "mean":
        state["mean"] = y.mean(0)
    elif name == "ridge":
        augmented = np.column_stack((np.ones(len(xx)), xx))
        penalty = np.eye(augmented.shape[1]) * config["alpha"]
        penalty[0, 0] = 0
        state["weights"] = linalg.solve(augmented.T @ augmented + penalty, augmented.T @ y, assume_a="pos")
    elif name == "knn":
        state.update(x=xx, y=y)
    elif name == "rbf":
        epsilon = 1 / np.sqrt(xx.shape[1])
        kernel = 1 / np.sqrt(1 + epsilon ** 2 * cdist(xx, xx, "sqeuclidean"))
        kernel.flat[::len(xx) + 1] += config["smoothing"]
        system = np.block([[kernel, np.ones((len(xx), 1))], [np.ones((1, len(xx))), np.zeros((1, 1))]])
        weights = linalg.solve(system, np.vstack((y, np.zeros((1, 2)))), assume_a="sym")
        state.update(x=xx, weights=weights, epsilon=np.asarray(epsilon))
    elif name == "gp_isotropic":
        kernel = np.exp(-0.5 * cdist(xx, xx, "sqeuclidean") / (xx.shape[1] * config["length"] ** 2))
        kernel.flat[::len(xx) + 1] += config["noise"] ** 2 + 1e-8
        state.update(x=xx, alpha=linalg.cho_solve(linalg.cho_factor(kernel, lower=True), y))
    elif name == "gp_ard":
        fitted, records = fit_ard(xx, y, config["kernel"])
        state.update(x=xx, **fitted)
        information["optimizer_starts"] = records
        information["output_kernel_policy"] = "independent_kernel_per_coordinate_training_likelihood_only"
    else:
        raise ValueError("unknown classical family")
    if any(not np.isfinite(value).all() for value in state.values()):
        raise ValueError("nonfinite classical state")
    return state, information


def predict_classical(config, state, q):
    q = representation(q, config.get("quality_weight", 1.0))
    name = config["family"]
    if name == "mean":
        return np.broadcast_to(state["mean"], (len(q), 2)).copy()
    if name == "ridge":
        return np.column_stack((np.ones(len(q)), q)) @ state["weights"]
    if name == "knn":
        k = min(config["k"], len(state["x"]))
        distance, index = cKDTree(state["x"]).query(q, k=k, workers=1)
        distance, index = distance.reshape(len(q), k), index.reshape(len(q), k)
        weights = 1 / np.maximum(distance, 1e-12)
        exact = distance < 1e-12
        weights = np.where(exact.any(1, keepdims=True), exact.astype(float), weights)
        return (state["y"][index] * weights[:, :, None]).sum(1) / weights.sum(1)[:, None]
    if name == "rbf":
        kernel = 1 / np.sqrt(1 + state["epsilon"] ** 2 * cdist(q, state["x"], "sqeuclidean"))
        return np.column_stack((kernel, np.ones(len(q)))) @ state["weights"]
    if name == "gp_isotropic":
        return np.exp(-0.5 * cdist(q, state["x"], "sqeuclidean") / (q.shape[1] * config["length"] ** 2)) @ state["alpha"]
    if name == "gp_ard":
        return np.column_stack([ard_kernel(q, state["x"], state["theta"][axis], config["kernel"]) @ state["alpha"][:, axis] for axis in range(2)])
    raise ValueError("unknown classical family")


def training_loss(prediction, target, y_scale, mode, smoothing_um=1.0):
    import torch
    if mode == "standardized_mse_control":
        return torch.mean((prediction - target) ** 2)
    if mode == "physical_euclidean":
        physical = (prediction - target) * y_scale
        return torch.mean(torch.sqrt(torch.sum(physical * physical, dim=1) + smoothing_um ** 2) - smoothing_um)
    raise ValueError("unknown paired loss")


def train_candidate(x, y, xv, yv, config, scaling, seed, mode):
    import os
    import resource
    import time
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch
    start = time.perf_counter()
    cpu = resource.getrusage(resource.RUSAGE_SELF)
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    if not torch.cuda.is_available():
        raise RuntimeError("2594-parameter training requires CUDA")
    total = torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(min(1.0, config["allocator_bytes"] / total), 0)
    torch.cuda.reset_peak_memory_stats()
    network = torch.nn.Sequential(torch.nn.Linear(24, 96), torch.nn.ReLU(), torch.nn.Linear(96, 2)).cuda()
    count = sum(p.numel() for p in network.parameters())
    if count != 2594:
        raise RuntimeError("registered architecture changed")
    tx, ty, tv = [torch.as_tensor(a, dtype=torch.float32, device="cuda") for a in (x, y, xv)]
    scale_tensor = torch.as_tensor(scaling.y_scale, dtype=torch.float32, device="cuda")
    optimizer = torch.optim.AdamW(network.parameters(), lr=config["learning_rate"], weight_decay=config["weight_decay"])
    best_error, best, best_epoch, history = float("inf"), None, None, []
    for epoch in range(config["epochs"]):
        optimizer.zero_grad(set_to_none=True)
        loss = training_loss(network(tx), ty, scale_tensor, mode, config["smoothing_um"])
        loss.backward()
        optimizer.step()
        with torch.no_grad():
            prediction = scaling.inverse(network(tv).cpu().numpy())
        validation = np.linalg.norm(prediction - yv, axis=1).mean()
        loss_value = float(loss.detach().cpu())
        history.append({"epoch": epoch + 1, "training_loss": loss_value if np.isfinite(loss_value) else None,
                        "validation_mean_error_um": float(validation) if np.isfinite(validation) else None})
        if np.isfinite(validation) and validation < best_error:
            best_error, best_epoch = float(validation), epoch + 1
            best = {name: parameter.detach().cpu().numpy().copy() for name, parameter in network.state_dict().items()}
    if best is None:
        best = {name: parameter.detach().cpu().numpy().copy() for name, parameter in network.state_dict().items()}
    torch.cuda.synchronize()
    end = resource.getrusage(resource.RUSAGE_SELF)
    return best, {"loss": mode, "training_seed": seed, "parameters": count, "epoch": best_epoch,
                  "training_device": "cuda", "validation_mean_error_um": best_error if np.isfinite(best_error) else None,
                  "history": history, "training_wall_seconds": time.perf_counter() - start,
                  "process_cpu_seconds_delta": end.ru_utime + end.ru_stime - cpu.ru_utime - cpu.ru_stime,
                  "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                  "receipt_scope": "diagnostic_central_job_receipt_is_authoritative"}


def predict_candidate(x, weights):
    x = np.asarray(x, dtype=np.float32)
    return np.maximum(x @ weights["0.weight"].T + weights["0.bias"], 0) @ weights["2.weight"].T + weights["2.bias"]
