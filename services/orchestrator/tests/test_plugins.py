from pathlib import Path

import pytest
from conftest import make_job

from die_firma.dag import depth, validate_dag
from die_firma.dispatcher import Dispatcher
from die_firma.models import Job, Plan
from die_firma.plugins import (
    BUILTIN_RULES,
    PluginRegistry,
    RuleBasedPlugin,
    ValidationResult,
    build_plan,
    default_registry,
    load_plugins_from_dir,
)


def test_default_registry_has_all_builtins():
    reg = default_registry()
    assert reg.types() == ["automation", "code_gen", "code_review", "data_prep"]


@pytest.mark.parametrize("job_type", list(BUILTIN_RULES))
def test_builtin_plugin_decomposes_to_valid_dag(job_type):
    plugin = default_registry().get(job_type)
    assert plugin is not None
    plan = plugin.decompose(make_job(type=job_type))
    validate_dag(plan.graph())
    assert depth(plan.graph()) <= 2


def test_register_rejects_duplicate_without_replace():
    reg = PluginRegistry()
    reg.register(RuleBasedPlugin("code_gen", BUILTIN_RULES["code_gen"]))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(RuleBasedPlugin("code_gen", BUILTIN_RULES["code_gen"]))
    # replace=True swaps it in.
    reg.register(RuleBasedPlugin("code_gen", BUILTIN_RULES["code_gen"]), replace=True)


def test_validator_runs_and_can_fail(tmp_path: Path):
    def deny(_job: Job, _wd: Path) -> ValidationResult:
        return ValidationResult(False, "nope")

    plugin = RuleBasedPlugin("code_gen", BUILTIN_RULES["code_gen"], validator=deny)
    res = plugin.validate(make_job(), tmp_path)
    assert res.passed is False and res.detail == "nope"


def test_no_validator_passes_by_default(tmp_path: Path):
    plugin = RuleBasedPlugin("code_gen", BUILTIN_RULES["code_gen"])
    assert plugin.validate(make_job(), tmp_path).passed is True


def test_dispatcher_uses_registered_plugin():
    reg = PluginRegistry()

    class TwoStep:
        task_type = "code_gen"

        def decompose(self, job: Job) -> Plan:
            return build_plan(job, [("implement", "x", []), ("smoke", "y", ["implement"])])

        def validate(self, job: Job, workdir: Path) -> ValidationResult:
            return ValidationResult(True)

    reg.register(TwoStep())
    plan = Dispatcher(registry=reg).plan(make_job(type="code_gen"))
    assert [s.action for s in plan.subtasks] == ["implement", "smoke"]


def test_dispatcher_validate_delegates(tmp_path: Path):
    reg = PluginRegistry()
    reg.register(
        RuleBasedPlugin(
            "code_gen",
            BUILTIN_RULES["code_gen"],
            validator=lambda j, w: ValidationResult(False, "blocked"),
        )
    )
    res = Dispatcher(registry=reg).validate(make_job(type="code_gen"), tmp_path)
    assert res.passed is False and res.detail == "blocked"


def test_load_plugins_from_dir_discovers_and_registers(tmp_path: Path):
    plugin_dir = tmp_path / "tasks"
    plugin_dir.mkdir()
    (plugin_dir / "_skip_me.py").write_text("raise RuntimeError('should be skipped')")
    (plugin_dir / "custom.py").write_text(
        "from die_firma.plugins import RuleBasedPlugin, BUILTIN_RULES\n"
        "def register(reg):\n"
        "    reg.register(RuleBasedPlugin('code_review', BUILTIN_RULES['code_review']),"
        " replace=True)\n"
    )
    reg = default_registry()
    added = load_plugins_from_dir(plugin_dir, reg)
    assert "code_review" in reg.types()
    # Re-registration of an existing type isn't a NEW type, so `added` is empty.
    assert added == []


def test_load_plugins_from_missing_dir_is_noop(tmp_path: Path):
    assert load_plugins_from_dir(tmp_path / "nope", default_registry()) == []


def test_example_plugin_flags_placeholders(tmp_path: Path):
    # The shipped example plugin (tasks/example_no_placeholders.py) overrides
    # code_gen with a no-placeholder validator. Exercise it directly.
    import importlib.util

    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "tasks" / "example_no_placeholders.py"
    spec = importlib.util.spec_from_file_location("example_np", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    reg = default_registry()
    mod.register(reg)
    plugin = reg.get("code_gen")
    assert plugin is not None

    (tmp_path / "app.py").write_text("def f():\n    pass  # TODO finish\n", encoding="utf-8")
    bad = plugin.validate(make_job(type="code_gen"), tmp_path)
    assert bad.passed is False and "app.py" in bad.detail

    (tmp_path / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    good = plugin.validate(make_job(type="code_gen"), tmp_path)
    assert good.passed is True
