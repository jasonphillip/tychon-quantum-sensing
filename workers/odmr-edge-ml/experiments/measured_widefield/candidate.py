"""Three prospectively fixed residual widths. CUDA training only; no added search."""
import numpy as np


def network(width=16):
    import torch
    if width not in (16, 32, 64):
        raise ValueError("Unregistered residual width")
    return torch.nn.Sequential(torch.nn.Linear(200, width), torch.nn.ReLU(), torch.nn.Linear(width, 200))


def train(inputs, targets, seed, width):
    import os
    if os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8":
        raise RuntimeError("Accounting must set CUBLAS_WORKSPACE_CONFIG=:4096:8 before Torch import")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("Candidate training requires CUDA; no CPU fallback")
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    model = network(width).cuda()
    assert sum(p.numel() for p in model.parameters()) == 401 * width + 200
    torch.nn.init.zeros_(model[-1].weight)
    torch.nn.init.zeros_(model[-1].bias)
    x = torch.as_tensor(inputs - 1, dtype=torch.float32, device="cuda")
    y = torch.as_tensor(targets - inputs, dtype=torch.float32, device="cuda")
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    generator = torch.Generator(device="cuda").manual_seed(seed)
    losses = []
    for _ in range(100):
        order = torch.randperm(len(x), generator=generator, device="cuda")
        total = 0.0
        for batch in order.split(64):
            optimizer.zero_grad(set_to_none=True)
            loss = torch.mean((model(x[batch]) - y[batch]) ** 2)
            loss.backward()
            optimizer.step()
            total += float(loss.detach().cpu()) * len(batch)
        losses.append(total / len(x))
    weights = {key: value.detach().cpu().numpy() for key, value in model.state_dict().items()}
    return weights, losses


def predict(inputs, weights):
    """Portable batch-1 NumPy deployment; training is the only CUDA stage."""
    import time
    output, failure, timing = [], [], []
    for values in inputs:
        start = time.perf_counter()
        hidden = np.maximum((values - 1) @ weights["0.weight"].T + weights["0.bias"], 0)
        result = values + hidden @ weights["2.weight"].T + weights["2.bias"]
        failed = not np.isfinite(result).all()
        if failed:
            result = values.copy()
        timing.append(time.perf_counter() - start)
        output.append(result)
        failure.append(failed)
    return np.asarray(output), np.asarray(failure), np.asarray(timing)
