"""The grounding guard AT RUNTIME — not as a test assertion.

This is the honesty guarantee. It has to hold for a real user in the deployed app,
not merely in a suite that runs offline. These tests drive `ask()` with a fake
Anthropic client, so they need no key and cost nothing, and they pin the whole
path: verify → one self-correction → withhold what still cannot be traced.
"""

import pytest

import src.agent.agent as agent_module
from src.agent.agent import AgentReply, ToolCall, ask
from src.agent.grounding import WITHHELD, verify

TOOL_RESULT = {
    "observed": [{"day": 197, "value": 3466.25}],
    "comparison": {"metrics": {"prophet": {"mae": 667.08}}},
}
CALLS = [ToolCall("get_forecast", {"analyte": "absolute_neutrophils"}, TOOL_RESULT)]


# --- verify() ---------------------------------------------------------------

def test_a_real_value_is_grounded():
    assert verify("The value at day 197 was 3466.25.", CALLS).ok


def test_a_faithful_rounding_is_grounded():
    """3466.255 -> "3466.26" is correct reporting, not fabrication. And Python's own
    round(14.075, 2) == 14.07, so comparing rounded values would reject the model's
    correct "14.08"."""
    assert verify("About 3466.3 cells.", CALLS).ok
    assert verify("MAE was 667.1.", CALLS).ok


def test_a_pairwise_difference_is_grounded():
    calls = [ToolCall("get_forecast", {}, {"a": 2910.75, "b": 1855.25})]
    assert verify("a drop of 1055.5", calls).ok


def test_a_tool_argument_is_grounded():
    """extra_days=103 is the agent's own request, not a claim about the data."""
    calls = [ToolCall("get_forecast", {"extra_days": 103}, {"day": 197})]
    assert verify("that is 103 days past day 197", calls).ok


def test_structural_constants_are_grounded():
    assert verify("n = 4 crew x 7 timepoints, FDR 0.05, 95% interval", CALLS).ok


def test_an_invented_number_is_NOT_grounded():
    result = verify("At day 300 it will be 5200.4.", CALLS)
    assert not result.ok
    assert "5200.4" in result.unverified


def test_an_approximation_is_not_grounded():
    """"~3,500" for a real 3466.25 puts a number in front of the reader that exists
    in no tool result. Even with a tilde."""
    result = verify("roughly 3500 cells", CALLS)
    assert not result.ok
    assert "3500" in result.unverified


def test_redaction_keeps_the_rest_of_the_answer():
    """An all-or-nothing block would throw away the reasoning, the caveats and any
    refusal just to suppress one number."""
    result = verify(
        "LightGBM cannot extrapolate. The value would be 9999.9. Do not trust it.",
        CALLS,
    )
    assert not result.ok
    assert WITHHELD in result.text
    assert "9999.9" not in result.text
    assert "cannot extrapolate" in result.text
    assert "Do not trust it." in result.text


# --- ask(): the runtime loop ------------------------------------------------

class FakeBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeResponse:
    stop_reason = "end_turn"

    def __init__(self, text):
        self.content = [FakeBlock(text)]


class FakeMessages:
    def __init__(self, drafts):
        self.drafts = list(drafts)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return FakeResponse(self.drafts.pop(0))


class FakeClient:
    def __init__(self, drafts):
        self.messages = FakeMessages(drafts)


@pytest.fixture
def fake(monkeypatch):
    def install(drafts):
        client = FakeClient(drafts)
        monkeypatch.setattr(agent_module, "build_client", lambda: client)
        # Pretend a tool already ran, so there is something to ground against.
        monkeypatch.setattr(agent_module, "verify", verify)
        return client
    return install


def _ask_with_calls(monkeypatch, client, question="q"):
    """Run ask() but inject a tool result, so grounding has real values."""
    original = agent_module.verify
    monkeypatch.setattr(
        agent_module, "verify", lambda text, calls: original(text, CALLS)
    )
    return ask(question)


def test_a_grounded_answer_passes_straight_through(fake, monkeypatch):
    client = fake(["The value at day 197 was 3466.25."])
    reply = _ask_with_calls(monkeypatch, client)

    assert reply.withheld == []
    assert reply.fully_grounded is True
    assert reply.self_corrected is False
    assert client.messages.calls == 1  # no retry needed


def test_an_ungrounded_answer_triggers_ONE_self_correction(fake, monkeypatch):
    """The model gets exactly one chance to fix itself, told which figures failed."""
    client = fake([
        "It will be 5200.4 at day 300.",        # ungrounded
        "The last observed value was 3466.25.",  # corrected
    ])
    reply = _ask_with_calls(monkeypatch, client)

    assert client.messages.calls == 2
    assert reply.self_corrected is True
    assert reply.withheld == []            # the correction worked
    assert "5200.4" not in reply.text


def test_a_persistently_ungrounded_answer_is_WITHHELD_not_shown(fake, monkeypatch):
    """The user must never see the unverifiable figure. This is the guarantee."""
    client = fake([
        "It will be 5200.4.",   # ungrounded
        "I insist: 5200.4.",    # still ungrounded after correction
    ])
    reply = _ask_with_calls(monkeypatch, client)

    assert client.messages.calls == 2      # one retry, then stop — no infinite loop
    assert reply.withheld == ["5200.4"]
    assert reply.fully_grounded is False
    assert "5200.4" not in reply.text      # the number never reaches the user
    assert WITHHELD in reply.text


def test_the_withheld_answer_is_still_a_usable_answer(fake, monkeypatch):
    """Graceful: not an error, not a hang, not a blank response. The reasoning and
    the refusal survive; only the figure is removed."""
    client = fake([
        "LightGBM cannot extrapolate; it would say 5200.4. Do not trust it.",
        "LightGBM cannot extrapolate; it would say 5200.4. Do not trust it.",
    ])
    reply = _ask_with_calls(monkeypatch, client)

    assert isinstance(reply, AgentReply)
    assert reply.text.strip()                       # not blank
    assert "cannot extrapolate" in reply.text       # reasoning survives
    assert "Do not trust it." in reply.text         # refusal survives
    assert "5200.4" not in reply.text               # only the figure is gone
    assert reply.withheld == ["5200.4"]


# --- the notice must not leak what it suppressed ----------------------------

def test_the_withhold_notice_never_prints_the_withheld_values(monkeypatch):
    """Regression: the first version listed them ("Withheld: 3600, 94.8"), putting
    the unverified numbers straight back in front of the reader — who could just
    take 3600 as the answer. A notice that re-exposes what it suppressed looks like
    a safeguard while defeating one."""
    import src.ui.assistant_page as page

    shown = []
    monkeypatch.setattr(page.st, "warning", lambda msg, **kw: shown.append(msg))

    page.withheld_notice(["3600", "94.8", "250"])

    assert shown, "a notice must be shown"
    message = shown[0]
    for leaked in ("3600", "94.8", "250"):
        assert leaked not in message, f"the notice leaked the withheld value {leaked}"

    assert "3 figures" in message      # the COUNT is disclosed
    assert "couldn't verify" in message
    assert WITHHELD in message          # and where to look in the text


def test_no_notice_when_nothing_was_withheld(monkeypatch):
    import src.ui.assistant_page as page

    shown = []
    monkeypatch.setattr(page.st, "warning", lambda msg, **kw: shown.append(msg))
    page.withheld_notice([])
    assert not shown


# --- the verifier is FINAL: the model may not argue with it ------------------

def test_a_withheld_answer_shows_only_the_neutral_message(monkeypatch):
    """The draft is where the arguing happens: it debates the check, claims its
    answer "stands", and reprints the very figures that were withheld. So on
    failure the draft is not rendered at all — one neutral message replaces it."""
    import src.ui.assistant_embed as embed

    shown = []
    monkeypatch.setattr(embed.st, "warning", lambda m, **k: shown.append(("warn", m)))
    monkeypatch.setattr(embed.st, "markdown", lambda m, **k: shown.append(("md", m)))

    argumentative = (
        "You're right — [withheld: unverified] was not a tool value, but 3520 is a "
        "false positive of the substring matcher. The rest of my answer stands."
    )
    embed._render_answer(argumentative, ["3520"])

    rendered = " ".join(m for _, m in shown)
    assert "3520" not in rendered, "the withheld figure was reprinted"
    assert WITHHELD not in rendered, "a [withheld] fragment leaked into prose"
    assert "stands" not in rendered, "the model argued with the verifier"
    assert "false positive" not in rendered, "verifier internals leaked"
    assert "could not be matched reliably" in rendered
    assert not any(kind == "md" for kind, _ in shown), "the draft must not be rendered"


def test_a_clean_answer_is_still_rendered_normally(monkeypatch):
    import src.ui.assistant_embed as embed

    shown = []
    monkeypatch.setattr(embed.st, "markdown", lambda m, **k: shown.append(m))
    monkeypatch.setattr(embed.st, "warning", lambda m, **k: shown.append(m))

    embed._render_answer("The value at day 197 was 3466.25.", [])
    assert shown == ["The value at day 197 was 3466.25."]
