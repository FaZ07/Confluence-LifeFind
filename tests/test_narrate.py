"""Optional narration layer — must be a perfectly transparent no-op without a key."""
import asyncio

import narrate


def test_disabled_by_default():
    """No GROQ_API_KEY in the environment -> narration is off."""
    assert narrate.enabled() is False


def test_polish_is_a_no_op_when_disabled():
    """With narration off, polish returns the deterministic text byte-for-byte and
    never touches the network (so this runs offline, instantly)."""
    text = "Marina Beach is the priority zone — 2 sources (The Hindu, Times of India) agree."
    out = asyncio.run(narrate.polish(text, child={"name": "Aarav Sharma"}))
    assert out == text


def test_redact_strips_the_subject_identity():
    """Whatever we would send must not contain the subject's name or its tokens."""
    text = "Aarav was last seen near Marina Beach; Aarav Sharma is 8 years old."
    safe = narrate._redact(text, {"name": "Aarav Sharma"})
    assert "Aarav" not in safe and "Sharma" not in safe
    assert "the subject" in safe
    assert "Marina Beach" in safe                 # operational detail is preserved


def test_redact_handles_missing_name():
    assert narrate._redact("plain text", None) == "plain text"
    assert narrate._redact("plain text", {}) == "plain text"
