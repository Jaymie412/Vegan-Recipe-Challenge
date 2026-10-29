# Vegan Recipe Challenge

A GenLayer Intelligent Contract that settles a friendly argument: **is this recipe really vegan?**

One person (the claimant) says a recipe is vegan and names a friend to challenge them. The challenger accepts the exact claim using its hash, and in that same transaction GenLayer validators each read the recipe and answer six yes/no questions: does it use meat, fish, dairy, egg, honey or gelatine? Every "yes" must quote the recipe word for word. **Code** checks the quotes, decides `vegan` or `not_vegan`, names the winner and updates both people's scores once.

Example: a "Creamy Tomato Pasta" with "2 tbsp butter" and "100ml double cream" is `not_vegan` (dairy), so the challenger wins.

## Why I built it

"Is this actually vegan?" comes up all the time when friends share recipes. Hidden ingredients like butter, honey or fish sauce are easy to miss. This contract makes a quick, fair call that anyone can check, because every "yes" points to the exact words in the recipe.

## How it stays fair

| Risk | How the contract handles it |
|---|---|
| Someone being challenged without agreeing | Nothing happens until the named challenger accepts the exact claim with `claim_hash`. The challenger can also decline. |
| The claimant editing the recipe after the challenge is accepted | The recipe is read **in the same transaction** as the acceptance, so there's no gap to change it. |
| A link to a different recipe | The AI must quote where the page names the dish, and **code** checks that the quote contains the recipe title. Otherwise the claim closes as **UNRELATED**: no winner, no score change. |
| A claim left open forever | Before acceptance, the claimant can cancel or the challenger can decline. After acceptance it settles at once. An unreadable page can be retried once by anyone, then closes as CLOSED_UNAVAILABLE with no score change. |
| Counting a result twice | One internal method updates scores. It refuses a claim already counted (a flag on the claim, plus `claim_ids` on both scores). |
| The AI making things up | Every "yes" needs a word-for-word quote, which code checks. The AI never outputs the verdict; code does. |
| Instructions hidden in a recipe | The recipe is treated as data. Validators audit the leader's answers for signs that hidden instructions were followed. |

## How consensus works

Using `gl.vm.run_nondet_unsafe`, the leader fetches the recipe and answers the eight questions (readable, names the dish, plus the six ingredient groups). Each validator fetches the recipe itself, answers every question independently, checks the leader's answers against the same strict rules, and must reach the **same label** (`vegan`, `not_vegan`, `unrelated` or `unreachable`). It then runs an AI audit of the leader's quotes and answers, returning `{"accept": true/false}`. Nothing is stored until all of this passes. A malformed AI reply is asked again, up to 3 times.

## Rules (code)

- `not_vegan` if any of meat, fish, dairy, egg, honey or gelatine is "yes"; `found` lists which.
- `vegan` if all six are "no". Plant milks are not dairy, and "may contain" warnings don't count.
- Winner: the claimant if `vegan`, the challenger if `not_vegan`. Each settled claim adds one win and one loss.

## Lifecycle

| Step | Who | Method | Status after |
|---|---|---|---|
| Make a claim | Claimant | `create_claim(challenger_address, recipe_title, recipe_url)` | OPEN (`claim_hash`) |
| Accept, and settle at once | Challenger | `accept_challenge(claim_id, expected_claim_hash)` | SETTLED, UNRELATED or UNREACHABLE |
| Or decline | Challenger | `decline_challenge(claim_id)` | DECLINED |
| Or cancel before acceptance | Claimant | `cancel_claim(claim_id)` | CANCELLED |
| Retry an unreadable page | Anyone | `retry_settle(claim_id)` | SETTLED, UNRELATED or CLOSED_UNAVAILABLE |

Read methods: `get_claim_summary`, `get_claim`, `get_score(address)`, `get_counts`, `get_policy`, `get_demo`, `get_demo_result`, `get_demo_summary`. Demo write: `run_demo(case_id)`.

## Quick start in Studio

1. Import `contract.py` into GenLayer Studio and deploy. There are no parameters.
2. Call `run_demo` with `case_id = 1` and wait for it to finish.
3. Call `get_demo_summary` with `result_id = 0`. Expected: label `vegan`, `matches_expected: true`, `records_created: false`.

See [DEMO_GUIDE.md](DEMO_GUIDE.md) for all six demos and the live walkthrough.

## Demonstrated in Studio

See [DEMO_RESULTS.md](DEMO_RESULTS.md) for the recorded run, deployment address and screenshots.

## Testing

`test_contract.py` contains 24 local tests using a simulated GenLayer runtime and authored AI answers. See [VERIFICATION.md](VERIFICATION.md).

## Boundaries

- This checks the written ingredient list only. It is not allergy, health or dietary advice, and it can't see what actually went into the pot.
- Ingredients that are sometimes animal-derived (some sugars, wines or E-numbers) are not checked unless the recipe says so.
- Binding proves the page names the dish, not who wrote it.
- The demos use fictional recipes. Real claims fetch the live page.
- All data is public on-chain.
- Instructions hidden in a recipe are treated as data. This reduces prompt injection but doesn't guarantee against it.
- Different addresses don't prove different people.

## Built with

- [GenLayer](https://docs.genlayer.com) Intelligent Contracts (Python, GenVM v0.2.16 runner)
- Developed with help from Claude
