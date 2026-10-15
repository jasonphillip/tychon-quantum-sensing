# What the models could not do: observations from this project

These are limits observed in this project, not a general model benchmark.
The numbered statements are editorial summaries; quoted fragments preserve source spelling.
Source: private export, not published, with public evidence links below.
For exported web chats: model version not recorded in the export.
Session-specific model identifiers appear on the linked exchange pages.

1. **Judge novelty or quality without flattering:** Gemini said “appears to be novel” and “exceptionally strong”, while Claude asserted “First-ever AI/ML integration in quantum sensor feedback loops”, without establishing those claims ([July 2](00-proposal-2025.md#1-begin-with-a-20-k-superconducting-qubit-controller--july-2-2025), [July 28](00-proposal-2025.md#4-refactor-the-proposal-for-room-temperature--july-28-2025), [August 1](00-proposal-2025.md#5-ask-for-flaws-and-number-checks--august-1-2025); the July 28 phrase is an additional visible-reply selection from that exchange).
2. **Check claims reliably:** local critics reduced false acceptances from 27 to 10 of 60 claims, but abstained on 58 % and 62.5 % of accepted claims were unsupported ([reported results](../../README.md#representative-results), [critic workflow](../../orchestrator/README.md#critic-independence)).
3. **See simulation's distance from reality without measured data:** a model warned about idealized lineshapes, yet default simulated lines remained 2–11 times too narrow against four public measured datasets ([review](playbook-creation-2026-03.md#p2), [measured comparison](../../workers/nv-sensor-sim/docs/external_validation_results.md)).
4. **Know a niche vendor toolchain:** speculative patching failed, and NotebookLM said the supplied manuals did not cover the specific question ([exchange and corrections](05-research-and-verification.md#1-stop-speculative-patching-and-ask-for-research)).
5. **Keep numbers consistent across documents:** checks found +2.107 ns versus +0.728 ns, a later visible reply opened “Three errors, one of them serious.” on May 31, and the 96.1 % ADEV figure held only at tau = 2,700 s ([timing comparison](building-additional-selections-2026.md#b2), [scorecard qualifications](building-additional-selections-2026.md#b3)).
6. **Hold context over months:** Claude misread the timeline from stale notes, illustrating why the [decision log](../docs/decision-log.md) and [dated status snapshot](../docs/status.md) exist ([correction](building-additional-selections-2026.md#b4)).
7. **Review their own work reliably:** another agent exposed a contract error and a review contradicted a claim about watchdog fallback ([contract correction](orchestration-and-publication-2026.md#c2), [fallback correction](orchestration-and-publication-2026.md#c4)).
8. **Do physical or licensed steps:** the April status snapshot still required a board boot and a license for AI inference runtime measurement ([historical scorecard](../docs/status.md#kpp-scorecard-r6_s25)).
9. **Own decisions:** scope, stop rules, publication, and export-control calls stayed with Jason, including decisions adopted from model advice ([human steering](human-steering.md), [Jason's attributed publication position](../../docs/proposal/README.md)).

Back to the [conversation record](README.md).
