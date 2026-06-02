"""Model router: pick the best local Ollama model for each unit of work.

Routing is two-dimensional (research-backed, see RUN_LOG):
  * by ROLE — what kind of work the sub-task is: writing code, reviewing/
    critiquing, multi-step reasoning, general writing, or looking at an image;
  * by DIFFICULTY — on a retry we escalate to a stronger reasoning model, since
    the first model already failed once ("Route-to-Reason", arXiv:2505.19435).

Deterministic and dependency-free so it stays unit-testable. Sensible defaults
are baked in; config.toml's [ollama.models] and [ollama.roles] override them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Job, Subtask

# Logical roles a sub-task can fall into.
CODE = "code"
REVIEW = "review"
REASON = "reason"
GENERAL = "general"
VISION = "vision"

# Sub-task action -> role. Anything unknown falls back in role_for() below.
_ACTION_ROLE: dict[str, str] = {
    "implement": CODE,
    "build_script": CODE,
    "self_review": REVIEW,
    "analyze": REVIEW,
    "smoke": REVIEW,
    "ingest": GENERAL,
    "transform": GENERAL,
}

# Baked-in defaults — every one of these is in the user's `ollama list`.
_DEFAULT_ROLE_MODELS: dict[str, str] = {
    CODE: "qwen2.5-coder:14b",
    REVIEW: "qwen2.5:14b",
    REASON: "deepseek-r1:14b",
    GENERAL: "qwen2.5:14b",
    VISION: "llava:7b",
}


@dataclass(frozen=True)
class Router:
    """Resolves (job, subtask, attempt) -> a concrete Ollama model name.

    `per_type` is the existing [ollama.models] map (code_gen -> model, …) and
    wins for CODE-role work so users keep that lever. `roles` ([ollama.roles])
    overrides any role default. `escalation_model` is used from the 2nd attempt
    onward regardless of role.
    """

    per_type: dict[str, str] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)
    default_model: str = "qwen2.5-coder:14b"
    escalation_model: str = "deepseek-r1:14b"

    def role_for(self, job: Job, subtask: Subtask) -> str:
        role = _ACTION_ROLE.get(subtask.action)
        if role is not None:
            return role
        # Unknown action: code-ish job types write code, everything else is general.
        return CODE if job.type in ("code_gen", "code_review", "automation") else GENERAL

    def _model_for_role(self, role: str, job: Job) -> str:
        # Explicit per-role override always wins.
        if role in self.roles:
            return self.roles[role]
        # CODE work honours the per-job-type map the user already maintains.
        if role == CODE:
            return self.per_type.get(job.type, self.default_model)
        if role == GENERAL:
            return self.per_type.get("data_prep") or _DEFAULT_ROLE_MODELS[GENERAL]
        return _DEFAULT_ROLE_MODELS.get(role, self.default_model)

    def model_for(self, job: Job, subtask: Subtask, attempt: int = 1) -> str:
        """Best model for this step. `attempt` is 1-based (matches the sentinel).

        On retry (attempt >= 2) we escalate to the reasoning model — the first
        model already failed, so throwing more raw reasoning at it pays off."""
        if attempt >= 2:
            return self.roles.get(REASON, self.escalation_model)
        return self._model_for_role(self.role_for(job, subtask), job)

    def vision_model(self) -> str:
        """Model used by the visual critic to look at a rendered screenshot."""
        return self.roles.get(VISION, _DEFAULT_ROLE_MODELS[VISION])

    def review_model(self) -> str:
        """Model used by the textual critique/review pass."""
        return self.roles.get(REVIEW, _DEFAULT_ROLE_MODELS[REVIEW])
