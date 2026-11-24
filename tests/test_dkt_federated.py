"""Registered FedAvg selection, release integrity and private deterministic demo selection."""

import copy

import pytest

from ml.dkt.common import DATA, SKILLS, json_read
from ml.dkt.demo_accounts import pick
from ml.dkt.fed_inference import model_info, predict
from ml.dkt.fed_verify import verify


def test_registered_commitment_and_cpu_export():
    info = verify()
    assert info["seeds"] == 3 and info["rounds"] == 180
    assert info["model_version"] == model_info()["model_version"]
    assert info["max_reference_error"] <= 1e-4
    assert set(predict([])) == set(SKILLS)
    assert predict([("fractions", False)]) != predict([("fractions", True)])


def test_prespecified_profiles_ignore_correctness_and_input_order():
    rules = json_read(DATA / "demo_selection.json")

    def events(skills):
        return [(i, s, i % 2) for i, s in enumerate(skills)]

    records = [
        ("u1", events([0, 1, 0])),
        ("u2", events([0] * 15)),
        ("u3", events([0, 1, 2, 3] * 10)),
    ]
    pools = {"validation": records, "test": []}
    selected = pick(pools, rules)
    alternate = {
        "validation": [
            (student, [(t, s, 1 - c) for t, s, c in seq])
            for student, seq in reversed(records)
        ],
        "test": [],
    }
    assert [x[1] for x in selected.values()] == [
        x[1] for x in pick(alternate, rules).values()
    ]
    assert len({s[1] for s in selected.values()}) == 3
    bad = copy.deepcopy(pools)
    bad["validation"] = bad["validation"][:2]
    with pytest.raises(ValueError, match="No non-training"):
        pick(bad, rules)


def test_weight_by_valid_target_count_including_bos_ignoring_padding():
    torch = pytest.importorskip("torch")
    pytest.importorskip("lightgbm")
    from ml.dkt.federated import add_weighted_state, valid_targets

    parts = [
        torch.tensor(0),
        torch.tensor(0),
        torch.tensor([[1.0, 0.0, -1.0], [0.0, -1.0, -1.0]]),
    ]
    assert valid_targets(parts) == 3
    total = {"p": torch.tensor([0.0], dtype=torch.float64)}
    add_weighted_state(total, {"p": torch.tensor([1.0])}, 1)
    add_weighted_state(total, {"p": torch.tensor([5.0])}, 3)
    assert (total["p"] / 4).item() == 4
    with pytest.raises(ValueError):
        add_weighted_state(total, {"p": torch.tensor([1.0])}, 0)
