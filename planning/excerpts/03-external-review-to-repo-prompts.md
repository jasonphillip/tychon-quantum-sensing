# 03 — External review output turned into one prompt per repo session

- Date: 2026-04-03 to 2026-04-04
- Context: Jason attaches a combined external review file. The project chat writes audit prompts for each repo session, then reads the replies and decides what each repo needs.
- Shows: spec -> prompt to a repo session, then result -> review, then review -> follow-up prompt.

### Spec -> prompt: audit prompts for repo 1

> **Jason:**
>
> i just got done creating 3 new repos that are replications of the old 3 but we scrubbed some info from them. NExt i want your thoughts on how the new preos could benifet from this gemeni outut items. First tell me an oiverview of how each could benifet, then give me prompts for each claude in each repo togather the info you needed to make recomendations on what we could change and why starting with r the new repo 1.
>
> **Claude (project chat):**
>
> **Prompt 3: Dataset [Interface] and Downstream Interface**
>
> > Show me the exact schema/manifest of what this repo produces as its output artifact — the dataset that Repo 2 (`odmr-edge-ml`) consumes. I need:
> > 1. File format and structure (keys, shapes, dtypes)
> > 2. The train/val/test split mechanism — how is data partitioned and are random seeds separated?
> > 3. The parameter distribution ranges for the test set vs training set — are they shifted to prevent inverse crime, or are they drawn from the same distribution?
> > 4. Any metadata stored alongside the data (generation config, noise parameters, git hash, etc.)
> > 5. The normalization scheme — are spectra normalized to [0,1]? Are B-field labels normalized? Is normalization done here or left to Repo 2?
> >
> > A reviewer flagged the anti-inverse-crime protocol as a strength but I need to verify it's actually implemented, not just documented.

### Result -> review -> follow-up: the audit finds a gap, the chat writes the fix prompt

> **Jason:**
>
> the claude on repo one was able to handle it all in one prompt:   please breakdown what the response means. Then tel me if we should give it a new prompt and also if you can give me the prompts for the other two repos to gather that info( as long as it doesnt depend on repo 1 claudes work) then do that as well
>
> **Claude (project chat):**
>
> **Prompt 3 (Dataset [Interface]): ONE CRITICAL FINDING.**
>
> Anti-inverse-crime is **documented but not implemented**. This is a real problem. Your report claims (and the Gemini ML Scientist praised) that train and test distributions are shifted to prevent the network from memorizing the simulator. But `generate_dataset()` passes identical parameter ranges to all splits. The only separation is random seeds. That's necessary but not sufficient — a skeptical reviewer will ask whether the network could invert the simulator rather than learn generalizable physics. You need to either implement shifted test ranges or reframe the report claim.
> […]
>
> **Repo 1 Follow-Up Prompt:**
>
> > The dataset contract audit found that the anti-inverse-crime protocol is documented but not implemented — `generate_dataset()` passes identical parameter ranges to all three splits (train/val/test). Only the random seeds differ.
> >
> > I need you to implement shifted test-set parameter distributions. Specifically:
> […]
>
> > This is blocking — the final report claims this separation exists and an ML reviewer specifically flagged it as a strength. It needs to actually be true.

### Next round: replies from repos 1 to 3 are judged

> **Jason:**
>
> here is the reponse from claude on repo one and let me know if we are keeping tack of wha was done and why we made he changes and also if i should give a prompt back to this claude:  also give me a summary of both repo 2 and 3 claudes output and what the prompt back to each should be: as far as that gemeni tracker log i will just uplad it to the project whe we are done for the day. This way you can keep making changes to it as we progress
>
> **Claude (project chat):**
>
> ## Repo 1 Status: DONE
>
> The anti-inverse-crime fix is solid. 55/55 tests passing, backward-compatible, manifest records whether shifts were used. The 12.5% mean shift / 20% width widening is well-calibrated — aggressive enough to catch memorization, conservative enough that it's not an adversarial test set. The insight about `inverse_crime_shift` being a manifest-level flag is good thinking — Repo 2's training loop can read that flag to know whether it's evaluating in-distribution or OOD.
>
> **No follow-up prompt needed for Repo 1.** It's clean. The only remaining Repo 1 item is the cosmetic `b_perp_range_T` comment fix (R1-5), which you can do yourself in 10 seconds or batch later.
> […]
>
> **Prompt 1 (Safety Gaps): All three GNC reviewer concerns are real.**
>
> Slew-rate limiting: the function exists (`apply_slew_limit()` in safety_clamps.cpp) with a defined constant (MAX_SLEW_PER_CYCLE = 0.001 = 200 V/ms at 200 MHz), but it's **commented out in the control path**. There's a TODO in nv_pid.cpp where it should be called. The safety triad claims slew-rate limiting as a pillar, but the code bypasses it.
> […]
>
> Bumpless transfer: the testbench exists and works, but it validates a **0.100 V delta, not the 0.076 V** claimed in the report. The 0.076 number doesn't appear anywhere in the codebase. Either the report number is wrong or it came from a different test configuration that's no longer reflected in code.

Result in the repos: repo 1 gained shifted test-set distributions with a manifest flag (55/55 tests); repo 2 gained sign folding in the training loop, default weight init and an export module with an operator check (87/87 tests); repo 3 findings went into a follow-up list.
