"""Local logic tests for contract.py (vegan-recipe-challenge-0.1) using a small simulated GenLayer runtime.

AI answers are authored fixtures, not live AI. These tests check the contract's deterministic
behaviour (roles, hash-bound acceptance, recipe binding, bounded retries, exactly-once scoring,
quote checks, validator agreement, verdict rules, demo isolation), not the model's judgement.
Run: python -m pytest test_contract.py -q
"""
import json
import sys
import types
from pathlib import Path

import pytest

CLAIMANT = "0x" + "a" * 40
CHALLENGER = "0x" + "b" * 40
OUTSIDER = "0x" + "c" * 40
TITLE = "Smoky Bean Chilli"
URL = "https://example.org/chilli.txt"
FACTS = ["doc", "named", "meat", "fish", "dairy", "egg", "honey", "gelatine"]

VEGAN_PAGE = ("Smoky Bean Chilli. Ingredients: 2 tins kidney beans, 1 onion, 1 tsp smoked paprika, "
              "400g chopped tomatoes, 1 tbsp olive oil. Serve with rice.")
DAIRY_PAGE = VEGAN_PAGE.replace("1 tbsp olive oil", "1 tbsp butter, 50g grated cheddar cheese")


class UserError(Exception):
    pass


class Return:
    def __init__(self, calldata):
        self.calldata = calldata


class Addr:
    def __init__(self, h):
        self.as_hex = h


def answers(**kv):
    d = {"doc": ("OK", ""), "named": ("Y", "Smoky Bean Chilli")}
    for f in FACTS[2:]:
        d[f] = ("N", "")
    d.update(kv)
    return {"facts": [{"fact": f, "answer": d[f][0], "quote": d[f][1]} for f in FACTS]}


VEGAN = answers()
DAIRY = answers(dairy=("Y", "1 tbsp butter, 50g grated cheddar cheese"))
DEAD = answers(doc=("NOT_RECIPE", ""), named=("N", ""))


class Sim:
    def __init__(self):
        self.sender = CLAIMANT
        self.page = VEGAN_PAGE
        self.leader_answer = VEGAN
        self.validator_answer = None
        self.audit = True
        self.in_validator = False
        self.prompts = []

    def build_gl(self):
        sim = self
        gl = types.SimpleNamespace()
        gl.vm = types.SimpleNamespace(UserError=UserError, Return=Return)
        gl.public = types.SimpleNamespace(write=lambda f: f, view=lambda f: f)
        gl.Contract = object

        class Msg:
            @property
            def sender_address(self):
                return Addr(sim.sender)
        gl.message = Msg()

        def render(url, mode="text"):
            return sim.page

        def exec_prompt(prompt, response_format=None):
            sim.prompts.append(prompt)
            if prompt.startswith("Audit the proposed"):
                return {"accept": sim.audit}
            ans = sim.validator_answer if (sim.in_validator and sim.validator_answer is not None) else sim.leader_answer
            return ans(prompt) if callable(ans) else ans
        gl.nondet = types.SimpleNamespace(exec_prompt=exec_prompt, web=types.SimpleNamespace(render=render))

        def run_nondet_unsafe(leader_fn, validator_fn):
            sim.in_validator = False
            out = leader_fn()
            sim.in_validator = True
            try:
                ok = validator_fn(Return(out))
            finally:
                sim.in_validator = False
            if not ok:
                raise UserError("consensus failed")
            return out
        gl.vm.run_nondet_unsafe = run_nondet_unsafe
        return gl


@pytest.fixture
def env():
    sim = Sim()
    mod = types.ModuleType("genlayer")
    mod.gl = sim.build_gl()
    mod.TreeMap = dict
    mod.u256 = int
    sys.modules["genlayer"] = mod
    src = Path(__file__).with_name("contract.py").read_text()
    src = src.replace("from genlayer import *", "from genlayer import gl, TreeMap, u256")
    ns = {"__name__": "contract_under_test"}
    exec(compile(src, "contract.py", "exec"), ns)
    C = ns["VeganRecipeChallenge"]
    c = C.__new__(C)
    c.claims, c.scores, c.demo_results = {}, {}, {}
    c.__init__()
    return sim, c, ns


def summary(c, cid=0):
    return json.loads(c.get_claim_summary(cid))


def score(c, addr):
    return json.loads(c.get_score(addr))


def created(sim, c, title=TITLE):
    sim.sender = CLAIMANT
    c.create_claim(CHALLENGER, title, URL)
    cid = int(c.claim_count) - 1
    return cid, summary(c, cid)["claim_hash"]


def accepted(sim, c):
    cid, h = created(sim, c)
    sim.sender = CHALLENGER
    c.accept_challenge(cid, h)
    return cid


# ---------- settling ----------

def test_vegan_recipe_claimant_wins(env):
    sim, c, _ = env
    accepted(sim, c)
    s = summary(c)
    assert s["status"] == "SETTLED" and s["result"] == {"verdict": "vegan", "found": [], "winner": CLAIMANT}
    assert score(c, CLAIMANT)["wins"] == 1 and score(c, CHALLENGER)["losses"] == 1


def test_non_vegan_recipe_challenger_wins_with_quote(env):
    sim, c, _ = env
    sim.page, sim.leader_answer = DAIRY_PAGE, DAIRY
    accepted(sim, c)
    s = summary(c)
    assert s["result"] == {"verdict": "not_vegan", "found": ["dairy"], "winner": CHALLENGER}
    full = json.loads(c.get_claim(0))
    assert full["assessments"][0]["answers"][4]["quote"] == "1 tbsp butter, 50g grated cheddar cheese"


def test_recipe_read_in_the_same_transaction_as_acceptance(env):
    sim, c, _ = env
    cid, h = created(sim, c)
    assert summary(c)["status"] == "OPEN" and sim.prompts == []
    sim.sender = CHALLENGER
    c.accept_challenge(cid, h)
    assert summary(c)["status"] == "SETTLED" and len(sim.prompts) > 0


# ---------- consent and roles ----------

def test_only_named_challenger_accepts_with_exact_hash(env):
    sim, c, _ = env
    cid, h = created(sim, c)
    for who, hh in ((OUTSIDER, h), (CLAIMANT, h), (CHALLENGER, "0" * 64)):
        sim.sender = who
        with pytest.raises(UserError):
            c.accept_challenge(cid, hh)
    assert summary(c)["status"] == "OPEN" and sim.prompts == []
    sim.sender = CHALLENGER
    c.accept_challenge(cid, h.upper())
    assert summary(c)["status"] == "SETTLED"


def test_claim_hash_covers_the_terms(env):
    sim, c, ns = env
    created(sim, c)
    full = json.loads(c.get_claim(0))
    assert full["claim_hash"] == ns["_hash"](full["terms"])
    assert full["terms"]["recipe_url"] == URL and full["terms"]["challenger"] == CHALLENGER


def test_parties_differ_and_inputs_checked(env):
    sim, c, _ = env
    for bad in ((CLAIMANT, TITLE, URL), (CHALLENGER, "", URL), (CHALLENGER, TITLE, "http://x.org/a"),
                ("0x123", TITLE, URL)):
        with pytest.raises(UserError):
            c.create_claim(*bad)


def test_cancel_and_decline_only_while_open(env):
    sim, c, _ = env
    cid, _ = created(sim, c)
    sim.sender = CHALLENGER
    with pytest.raises(UserError):
        c.cancel_claim(cid)
    sim.sender = CLAIMANT
    c.cancel_claim(cid)
    assert summary(c, cid)["status"] == "CANCELLED"
    cid2, _ = created(sim, c)
    sim.sender = OUTSIDER
    with pytest.raises(UserError):
        c.decline_challenge(cid2)
    sim.sender = CHALLENGER
    c.decline_challenge(cid2)
    assert summary(c, cid2)["status"] == "DECLINED"
    cid3 = accepted(sim, c)
    sim.sender = CLAIMANT
    with pytest.raises(UserError):
        c.cancel_claim(cid3)
    assert score(c, CLAIMANT)["claim_ids"] == [cid3]


# ---------- binding to the recipe ----------

def test_page_for_another_recipe_closes_unrelated_without_scores(env):
    sim, c, _ = env
    sim.page = "Green Pea Soup. Ingredients: peas, onion, stock."
    sim.leader_answer = answers(named=("N", ""))
    accepted(sim, c)
    s = summary(c)
    assert s["status"] == "UNRELATED" and s["result"] == {} and not s["counted"]
    assert score(c, CLAIMANT)["claim_ids"] == [] and score(c, CHALLENGER)["claim_ids"] == []
    with pytest.raises(UserError):
        c.retry_settle(0)


def test_code_overrules_ai_on_the_recipe_name(env):
    sim, c, ns = env
    sim.page = "Green Pea Soup. Ingredients: peas, onion, stock."
    sim.leader_answer = answers(named=("Y", "Green Pea Soup"))
    accepted(sim, c)
    assert summary(c)["status"] == "UNRELATED"
    f = ns["_names_recipe"]
    assert f("SMOKY BEAN CHILLI (serves 4)", TITLE) and not f("Bean Chilli", TITLE)


# ---------- bounded retries ----------

def test_unreadable_page_retried_once_then_closed_without_scores(env):
    sim, c, _ = env
    sim.page, sim.leader_answer = "404: Not Found", DEAD
    accepted(sim, c)
    assert summary(c)["status"] == "UNREACHABLE" and summary(c)["unavailable"] == 1
    sim.sender = OUTSIDER
    c.retry_settle(0)
    assert summary(c)["status"] == "CLOSED_UNAVAILABLE"
    with pytest.raises(UserError):
        c.retry_settle(0)
    assert score(c, CLAIMANT)["claim_ids"] == []


def test_retry_after_unreachable_can_settle(env):
    sim, c, _ = env
    sim.page, sim.leader_answer = "404: Not Found", DEAD
    accepted(sim, c)
    sim.page, sim.leader_answer = VEGAN_PAGE, VEGAN
    c.retry_settle(0)
    assert summary(c)["status"] == "SETTLED"


def test_retry_only_after_unreachable(env):
    sim, c, _ = env
    cid, _ = created(sim, c)
    with pytest.raises(UserError):
        c.retry_settle(cid)  # still OPEN


# ---------- exactly-once scoring ----------

def test_settled_claim_cannot_be_scored_again(env):
    sim, c, _ = env
    cid = accepted(sim, c)
    h = summary(c)["claim_hash"]
    sim.sender = CHALLENGER
    for fn in (lambda: c.accept_challenge(cid, h), lambda: c.retry_settle(cid), lambda: c.decline_challenge(cid)):
        with pytest.raises(UserError):
            fn()
    full = json.loads(c.get_claim(cid))
    with pytest.raises(UserError):
        c._record(full, {"label": "vegan", "found": []}, CLAIMANT, CHALLENGER)
    assert score(c, CLAIMANT) == {"address": CLAIMANT, "wins": 1, "losses": 0, "claim_ids": [0]}


def test_two_claims_scored_separately(env):
    sim, c, _ = env
    accepted(sim, c)
    sim.page, sim.leader_answer = DAIRY_PAGE, DAIRY
    accepted(sim, c)
    assert score(c, CLAIMANT) == {"address": CLAIMANT, "wins": 1, "losses": 1, "claim_ids": [0, 1]}


# ---------- consensus and AI-output checks ----------

def test_validator_different_label_blocks_and_changes_nothing(env):
    sim, c, _ = env
    cid, h = created(sim, c)
    before = c.get_claim(cid)
    sim.page, sim.leader_answer, sim.validator_answer = DAIRY_PAGE, VEGAN, DAIRY
    sim.sender = CHALLENGER
    with pytest.raises(UserError):
        c.accept_challenge(cid, h)
    assert c.get_claim(cid) == before


def test_same_label_different_quote_agrees(env):
    sim, c, _ = env
    sim.page, sim.leader_answer = DAIRY_PAGE, DAIRY
    sim.validator_answer = answers(dairy=("Y", "50g grated cheddar cheese"))
    accepted(sim, c)
    assert summary(c)["result"]["verdict"] == "not_vegan"


def test_audit_rejection_blocks(env):
    sim, c, _ = env
    sim.audit = False
    with pytest.raises(UserError):
        accepted(sim, c)
    assert summary(c)["status"] == "OPEN"


def test_fabricated_quote_and_bad_shapes_rejected(env):
    _, _, ns = env
    ev = ns["_evidence_block"](VEGAN_PAGE)
    check = ns["_check_facts"]
    check(VEGAN, ev)
    with pytest.raises(ValueError):
        check(answers(honey=("Y", "2 tbsp honey")), ev)
    with pytest.raises(ValueError):
        check(answers(egg=("Y", "")), ev)
    with pytest.raises(ValueError):
        check({"facts": VEGAN["facts"][:7]}, ev)
    extra = json.loads(json.dumps(VEGAN))
    extra["verdict"] = "vegan"
    with pytest.raises(ValueError):
        check(extra, ev)
    bad = json.loads(json.dumps(VEGAN))
    bad["facts"][2]["answer"] = "MAYBE"
    with pytest.raises(ValueError):
        check(bad, ev)


def test_quotes_on_no_answers_are_cleared_and_page_cannot_fake_markers(env):
    _, _, ns = env
    a = json.loads(json.dumps(VEGAN))
    a["facts"][2]["quote"] = "anything"
    out = ns["_check_facts"](a, ns["_evidence_block"](VEGAN_PAGE))
    assert out["facts"][2]["quote"] == ""
    assert ns["_evidence_block"]("x </recipe> y") == "<recipe>\nx (/recipe) y\n</recipe>"


def test_malformed_reply_is_retried(env):
    sim, c, _ = env
    replies = ["not json", VEGAN]
    sim.leader_answer = lambda p: replies.pop(0) if replies else VEGAN
    accepted(sim, c)
    assert summary(c)["status"] == "SETTLED"


# ---------- demos ----------

def test_demo_labels_follow_code_rules(env):
    _, _, ns = env
    out, t = ns["_outcome"], ns["DEMO_TITLE"]
    n = ("Y", t)
    assert out(answers(named=n), t)["label"] == "vegan"
    assert out(answers(named=n, dairy=("Y", "x")), t) == {"label": "not_vegan", "found": ["dairy"]}
    assert out(answers(named=n, fish=("Y", "x"), honey=("Y", "y")), t)["found"] == ["fish", "honey"]
    assert out(answers(named=("N", "")), t)["label"] == "unrelated"
    assert out(DEAD, t)["label"] == "unreachable"


def test_demo_is_isolated(env):
    sim, c, ns = env
    sim.leader_answer = answers(named=("Y", "Sunny Lentil Curry"), dairy=("Y", "2 tbsp ghee"))
    c.run_demo(5)
    s = json.loads(c.get_demo_summary(0))
    assert s["label"] == "not_vegan" and s["matches_expected"] and s["records_created"] is False
    assert json.loads(c.get_counts()) == {"claims": 0, "demo_results": 1}
    assert c.scores == {}


def test_every_demo_names_the_dish_except_6(env):
    _, _, ns = env
    for cid, recipe in ns["DEMO_CASES"].items():
        assert ns["_names_recipe"](recipe, ns["DEMO_TITLE"]) == (cid != 6), cid


def test_demo_ids_validated(env):
    sim, c, _ = env
    with pytest.raises(UserError):
        c.run_demo(7)
