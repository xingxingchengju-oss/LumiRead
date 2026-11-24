"""Optional training-environment regressions for target alignment and baseline feature leakage."""

import pytest

pytest.importorskip("torch")
pytest.importorskip("lightgbm")


def test_only_prefix_responses_enter_features():
    import torch

    from ml.baselines.lightgbm import features
    from ml.dkt.dataset import tensors

    a = [[(0, 1), (2, 0), (2, 1)]]
    b = [[(0, 1), (2, 1), (2, 1)]]
    x, _, _ = tensors(a, torch.device("cpu"))
    x2, _, _ = tensors(b, torch.device("cpu"))
    assert x.tolist() == [[0, 2, 5]]
    assert x2.tolist() == [[0, 2, 6]]
    xb, _, _ = features(a)
    xb2, _, _ = features(b)
    assert (xb[:2] == xb2[:2]).all()
    assert not (xb[2] == xb2[2]).all()
