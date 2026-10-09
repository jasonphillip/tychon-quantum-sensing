# How the orchestration loop worked, in the chat's own words

I kept one long-running project chat as the planning layer and ran a separate coding-agent session for each repository. The four conversations here follow the same loop. Claude, in the project chat, turns a plan or a batch of findings into a prompt for one repo session, and I paste the prompt in. The repo session replies, usually with a plan or a test summary, and that reply goes back into the project chat. Claude then judges it, says what is wrong or missing, and writes the next prompt. Each pass ends with tests, a commit or a corrected claim.

The excerpts are verbatim. Cuts are marked "[…]", and every redaction is marked in brackets.

- 01-build-order-and-interfaces.md: build order for three repos, a snapshot review, and the first planning prompt for repo 2.
- 02-ou-noise-wiring-prompt-and-review.md: a plan-mode prompt, the session's plan, a flaw in the premise, and the decision.
- 03-external-review-to-repo-prompts.md: an external review file turned into audit prompts, then fix prompts per repo.
- 04-fixing-claims-and-pausing-a-plan.md: a tied-off signal found in an FPGA build, a fix prompt, and a session that pushes back.
