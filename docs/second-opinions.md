# Second opinions: where another model caught a mistake

Most of the work ran through one planning chat and the coding agents. For some problems I asked a different model on purpose.

- Gemini Deep Think for math and physics, where it was the strongest model I had at the time.
- ChatGPT Pro to review a plan or a patch that another model had written.
- Claude, with the project files at hand, to check numbers before they went into a document.

No single model was right every time, including the ones I trusted most.

The examples below come from my chat history. I found them by running a classifier (TypeSafe's Jev model) over about 1,100 project-related conversations and then reading the top candidates. The quotes are exact, and the model names come from the chats themselves, because the exports don't record them.

## A made-up physics floor in a simulator patch (2026-03-11)

The simulator produced linewidths for high-purity diamond that were too narrow for its frequency grid. Gemini proposed a fix in the physics code, to "create a hard inhomogeneous broadening floor of about 1.0 to 1.5 MHz".

I gave that patch to ChatGPT Pro. It answered that the fixed floor "is not a universal rule". It kept the grid fix, asked for a numerical grid check and a configurable, sample-specific broadening term, and pointed out that the replacement dephasing table had no source.

Gemini wrote back that "The critique is absolutely correct" and revised the task for the coding agent. In the new version the floor is gone, the broadening default is zero and a cited scaling law replaces the table.

## A unit error that made a navigation claim about 100 times too good (2026-04-02)

In a draft report, a drift figure had been turned into a 1 km navigation-error claim. The drift was in microtesla, not nanotesla. Gemini caught it and wrote, "If your sensor truly drifts by 2.35 µT (2,350 nT), your absolute MagNav CEP is physically limited to around ~117 km, not 1 km."

Claude Code then checked the units in the code, and the result came back as "The Claude Code audit confirms the full unit chain: T → µT (×1e6), no nT conversion anywhere." Only the relative improvement (6.3×) went into the short brief, and the navigation claim was rewritten later.

## Where the fp32 gain went in INT8 (2026-05-02)

The ML correction cut error roughly in half in fp32 simulation but by only 5 to 7% once deployed in INT8. The deployed scalar INT8 model ends at about 4.9% lower error than a synthetic PID proxy, on synthetic data. I asked Gemini Deep Think to bound each possible cause. It put quantization at under one point and the rest on saturation plus distribution shift: "Because $s_f \approx s_c$, the cascade collapses." Its recommendation was "Bias-Aware Augmentation First".

That split was adopted in the plan of 2026-05-15, with bias-aware augmentation as the top priority. A later run showed a fine-stage clip fraction of 0.939, which supports the saturation finding. That run's log is not in this repository.

## Checking a results table before it was used (2026-05-31)

A metrics table had gone to two models. Claude checked it against the project files and found that "the held-out set is **n=5,000**, not 50K". The timing row had the wrong worst-slack value and the wrong clock domain. I asked for the verified numbers to be used from then on.

## Pushing back on reviews (2026-07-08)

In three reviews, Gemini recommended continual-learning fixes for an accuracy drop. A push-back on those reviews said "EWC is misapplied", because the model was trained from scratch and forgetting wasn't the failure. Gemini replied, "I completely concede the errors", and the next step was planned around the ideas that survived (distillation, geometry-weighted loss, gradient surgery).
