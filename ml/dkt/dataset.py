"""Sequences and prefix-only model inputs. The order matches the private split manifest."""

import json

from .common import CACHE, DATA, json_read, sha256


def read_split(split):
    path = CACHE / f"{split}.jsonl"
    expected = json_read(DATA / "summary.json")["splits"][split]["sequence_sha256"]
    if sha256(path) != expected:
        raise ValueError(
            f"Private {split} data failed digest check. Run ml.dkt.prepare."
        )
    records = [json.loads(line) for line in path.read_text().splitlines()]
    return [[(skill, correct) for _, skill, correct in events] for _, events in records]


def tensors(sequences, device):
    import torch

    n = len(sequences)
    width = max(map(len, sequences))
    inputs = torch.zeros((n, width), dtype=torch.long)
    skills = torch.zeros_like(inputs)
    targets = torch.full((n, width), -1.0)
    for i, seq in enumerate(sequences):
        source = torch.tensor(seq)
        length = len(seq)
        skills[i, :length] = source[:, 0]
        targets[i, :length] = source[:, 1]
        inputs[i, 1:length] = 1 + 2 * source[:-1, 0] + source[:-1, 1]
    return tuple(x.to(device) for x in (inputs, skills, targets))


def batches(sequences, batch_size, rng=None):
    # Adjacent sequence lengths limit padding. Shuffle the buckets and membership each epoch.
    if rng is None:
        indexes = list(range(len(sequences)))
    else:
        indexes = rng.permutation(len(sequences)).tolist()
    packed = []
    for i in range(0, len(indexes), 6 * batch_size):
        pool = (
            sorted(indexes[i : i + 6 * batch_size], key=lambda j: len(sequences[j]))
            if rng is not None
            else indexes[i : i + 6 * batch_size]
        )
        packed.extend(
            [pool[j : j + batch_size] for j in range(0, len(pool), batch_size)]
        )
    if rng is not None:
        rng.shuffle(packed)
    for block in packed:
        yield [sequences[j] for j in block]
