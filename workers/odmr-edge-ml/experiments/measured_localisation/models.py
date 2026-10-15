"""Vectorized strong references and a bounded, prospective MLP width grid."""
import numpy as np
from scipy import linalg
from scipy.interpolate import RBFInterpolator
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


def fit_classical(name, config, x, y):
    if name == "mean":
        mean = y.mean(0)
        return lambda q: np.broadcast_to(mean, (len(q), 2)).copy()
    if name == "ridge":
        xx = np.column_stack((np.ones(len(x)), x))
        penalty = np.eye(xx.shape[1]) * config["alpha"]
        penalty[0, 0] = 0
        weights = linalg.solve(xx.T @ xx + penalty, xx.T @ y, assume_a="pos")
        return lambda q: np.column_stack((np.ones(len(q)), q)) @ weights
    if name == "knn":
        tree = cKDTree(x)
        k = min(config["k"], len(x))

        def predict(q):
            distance, index = tree.query(q, k=k, workers=1)
            distance, index = distance.reshape(len(q), k), index.reshape(len(q), k)
            weights = 1 / np.maximum(distance, 1e-12)
            exact = distance < 1e-12
            weights = np.where(exact.any(1, keepdims=True), exact.astype(float), weights)
            return (y[index] * weights[:, :, None]).sum(1) / weights.sum(1)[:, None]

        return predict
    if name == "rbf":
        return RBFInterpolator(x, y, kernel="inverse_multiquadric", epsilon=1 / np.sqrt(x.shape[1]),
                               degree=0, smoothing=config["smoothing"])
    if name == "gp":
        length = config["length"]
        kernel = np.exp(-0.5 * cdist(x, x, "sqeuclidean") / (x.shape[1] * length ** 2))
        kernel.flat[::len(x) + 1] += config["noise"] ** 2 + 1e-8
        weights = linalg.cho_solve(linalg.cho_factor(kernel, lower=True), y)
        return lambda q: np.exp(-0.5 * cdist(q, x, "sqeuclidean") / (x.shape[1] * length ** 2)) @ weights
    raise ValueError("unknown classical reference: " + name)


def train_candidate(x, y, xv, yv, config, scaling, seed):
    import os
    import resource
    import time
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch
    wall_start = time.perf_counter()
    usage_start = resource.getrusage(resource.RUSAGE_SELF)
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    width = config["hidden"]
    network = torch.nn.Sequential(torch.nn.Linear(24, width), torch.nn.ReLU(), torch.nn.Linear(width, 2))
    count = sum(p.numel() for p in network.parameters())
    if count != config["parameters"]:
        raise RuntimeError("candidate parameter count changed")
    device = config.get("device", "cuda" if count > 1000 else "cpu")
    if count > 1000 and device != "cuda":
        raise RuntimeError("training above 1000 parameters requires CUDA")
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("training above 1000 parameters requires CUDA")
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    network.to(device)
    tx, ty, tv = [torch.as_tensor(a, dtype=torch.float32, device=device) for a in (x, y, xv)]
    optimizer = torch.optim.AdamW(network.parameters(), lr=config["learning_rate"], weight_decay=config["weight_decay"])
    best_loss, best, best_epoch = float("inf"), None, None
    for epoch in range(config["epochs"]):
        optimizer.zero_grad(set_to_none=True)
        loss = torch.mean((network(tx) - ty) ** 2)
        loss.backward()
        optimizer.step()
        with torch.no_grad():
            prediction = scaling.inverse(network(tv).cpu().numpy())
        validation = np.linalg.norm(prediction - yv, axis=1).mean()
        if np.isfinite(validation) and validation < best_loss:
            best_loss, best_epoch = float(validation), epoch + 1
            best = {name: p.detach().cpu().numpy().copy() for name, p in network.state_dict().items()}
    if best is None:
        raise RuntimeError("candidate produced no finite validation checkpoint")
    if device == "cuda":
        torch.cuda.synchronize()
    usage_end = resource.getrusage(resource.RUSAGE_SELF)
    wall = time.perf_counter() - wall_start
    return best, {"validation_mean_error_um": best_loss, "epoch": best_epoch,
                  "parameters": count, "hidden": width, "training_device": device,
                  "training_wall_seconds": wall,
                  "process_cpu_seconds_delta": usage_end.ru_utime + usage_end.ru_stime - usage_start.ru_utime - usage_start.ru_stime,
                  "gpu_training_wall_seconds": wall if device == "cuda" else 0.0,
                  "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated() if device == "cuda" else 0,
                  "resource_receipt_scope": "per_configuration_diagnostic_central_job_receipt_is_authoritative"}


def predict_candidate(x, weights):
    # Exact architecture in vectorized NumPy; includes no framework startup timing claim.
    x = np.asarray(x, dtype=np.float32)
    return np.maximum(x @ weights["0.weight"].T + weights["0.bias"], 0) @ weights["2.weight"].T + weights["2.bias"]
