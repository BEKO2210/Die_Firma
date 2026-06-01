import pytest
from conftest import make_job

from die_firma.dag import depth, validate_dag
from die_firma.dispatcher import Dispatcher, decompose_rule_based


@pytest.mark.parametrize("job_type", ["code_gen", "code_review", "automation", "data_prep"])
def test_decompose_each_type_is_valid_shallow_dag(job_type):
    job = make_job(type=job_type)
    plan = decompose_rule_based(job)
    assert plan.subtasks
    graph = plan.graph()
    validate_dag(graph)  # would raise on cycle / >2 depth
    assert depth(graph) <= 2
    for st in plan.subtasks:
        assert st.id.startswith(job.id + ":")


def test_dispatcher_plan_uses_rule_based():
    job = make_job(type="code_gen")
    plan = Dispatcher().plan(job)
    assert [s.action for s in plan.subtasks] == ["implement", "self_review"]
    assert plan.subtasks[1].depends_on == [plan.subtasks[0].id]
