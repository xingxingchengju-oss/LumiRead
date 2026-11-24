"""Runtime regression tests run in the ordinary app environment without training packages."""

import copy
import shutil

import pytest

from ml.dkt.common import ARTIFACTS, SKILLS
from ml.dkt.inference import ModelUnavailable, _bundle, model_info, predict
from ml.dkt.prepare import split_students
from ml.dkt.verify import verify


def test_frozen_cpu_bundle_matches_training_device():
    result = verify()
    assert result["max_abs_error"] <= 1e-4
    assert result["reference_outputs"] >= len(SKILLS) * 3
    assert model_info() == {
        "model_version": result["model_version"],
        "device": "cpu",
        "available": True,
    }


def test_same_history_roundtrips_and_order_matters():
    history = [("fractions", True), ("equations", False)]
    before = copy.deepcopy(history)
    original = predict(history)
    assert history == before
    assert predict(list(history)) == original
    assert list(original) == list(SKILLS)
    assert all(0 < p < 1 for p in original.values())
    assert predict(history[::-1]) != original
    assert predict([("fractions", True)]) != predict([("fractions", False)])
    assert predict([]) != original


@pytest.mark.parametrize(
    "history", [[("typo", True)], [("area", 1)], [("area", "false")]]
)
def test_invalid_attempts_are_explicit(history):
    with pytest.raises(ValueError):
        predict(history)


def test_fails_on_missing_or_corrupted_model(tmp_path):
    with pytest.raises(ModelUnavailable):
        _bundle(tmp_path)
    shutil.copy(ARTIFACTS / "checksums.json", tmp_path)
    weight_file = tmp_path / "cpu_weights.json"
    shutil.copy(ARTIFACTS / "cpu_weights.json", weight_file)
    _bundle(tmp_path)
    weight_file.unlink()
    with pytest.raises(ModelUnavailable):
        _bundle(tmp_path)
    weight_file.write_text("{}")
    with pytest.raises(ModelUnavailable, match="SHA-256"):
        _bundle(tmp_path)


def test_student_split_is_deterministic_and_disjoint():
    members = [str(i) for i in range(100)]
    splits = split_students(members)
    assert splits == split_students(reversed(members))
    assert [len(splits[k]) for k in ("train", "validation", "test")] == [70, 15, 15]
    assert len(set().union(*map(set, splits.values()))) == sum(
        map(len, splits.values())
    )
