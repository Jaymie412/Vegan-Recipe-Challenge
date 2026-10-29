# Vegan Recipe Challenge verification

Contract file: `contract.py`, version `vegan-recipe-challenge-0.1`.

## Local checks completed

- Python syntax compilation succeeded.
- `test_contract.py`: **24 tests passed** against a simulated GenLayer runtime.
- Every GenLayer SDK call the contract uses (`gl.vm.run_nondet_unsafe`, `gl.vm.Return`, `gl.nondet.exec_prompt`, `gl.nondet.web.render`, `gl.vm.UserError`, `gl.message.sender_address`) is used the same way by my earlier contracts, which ran end to end on GenLayer Studio with the same `py-genlayer` runner.

The official `genlayer-test` package couldn't be installed in the environment used, so the tests use a small simulated runtime. All AI answers in the tests are authored fixtures. They check the contract's deterministic behaviour, not the AI's judgement.

## What the tests cover

**Settling**
1. A vegan recipe: SETTLED, the claimant wins, and both scores update.
2. A recipe with butter and cheese: `not_vegan`, `found` = dairy, the challenger wins, and the quote is stored.
3. The recipe is read in the same transaction as the acceptance; nothing is read while the claim is open.

**Consent and roles**
4. Only the named challenger can accept, and only with the exact `claim_hash` (case ignored). The claimant and outsiders are refused.
5. The claim hash covers the challenger, the title and the link.
6. Claimant and challenger must differ; https links only; titles and addresses are checked.
7. Only the claimant can cancel and only the challenger can decline, both only while the claim is open.

**Binding to the recipe**
8. A page for another dish closes as UNRELATED: no winner, no score change, no retry.
9. If the AI claims another dish's name matches, code overrules it; a partial name doesn't count.

**Bounded retries**
10. An unreadable page: UNREACHABLE, one retry by anyone, then CLOSED_UNAVAILABLE with no scores.
11. A retry that can read the page settles normally.
12. A retry is only possible after UNREACHABLE.

**Exactly-once scoring**
13. A settled claim can't be accepted, retried or declined again, and a direct internal replay is refused.
14. Two claims are each scored once.

**Consensus and AI-output checks**
15. A validator reaching a different label blocks the transaction and leaves the claim unchanged.
16. Validators quoting different words but reaching the same label still agree.
17. A failed audit blocks the transaction.
18. Fabricated quotes, empty quotes on "yes", missing or extra facts, extra fields and unknown answers are rejected.
19. Quotes on "no" answers are cleared; the page can't fake the evidence section markers.
20. A malformed AI reply is asked again.

**Demos**
21. The labels follow the code rules; demos create no claims or scores; every demo recipe names the dish except demo 6.

## Live Studio evidence

See [DEMO_RESULTS.md](DEMO_RESULTS.md).
