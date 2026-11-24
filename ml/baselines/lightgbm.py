"""LightGBM knowledge tracing using only the target skill and responses already observed."""

import lightgbm as lgb
import numpy as np

from ml.dkt.common import SEED, SKILLS

FEATURES = [
    "skill",
    "prior_n",
    "prior_rate",
    "skill_n",
    "skill_rate",
    "last_response",
    "last_skill_response",
    "same_skill_as_previous",
    "gap_since_skill",
    "recent_five_rate",
]


def features(sequences):
    rows, labels, skills = [], [], []
    for events in sequences:
        seen, right, last_seen, last_right = (
            [0] * len(SKILLS),
            [0] * len(SKILLS),
            [-1] * len(SKILLS),
            [-1] * len(SKILLS),
        )
        history = []
        total_right = 0
        prev_skill = -1
        for t, (s, correct) in enumerate(events):
            recent = history[-5:]
            rows.append(
                [
                    s,
                    t,
                    (total_right + 1) / (t + 2),
                    seen[s],
                    (right[s] + 1) / (seen[s] + 2),
                    history[-1] if history else -1,
                    last_right[s],
                    int(s == prev_skill),
                    t - last_seen[s] if seen[s] else -1,
                    sum(recent) / len(recent) if recent else 0.5,
                ]
            )
            labels.append(correct)
            skills.append(s)
            seen[s] += 1
            right[s] += correct
            last_seen[s], last_right[s] = t, correct
            history.append(correct)
            total_right += correct
            prev_skill = s
    return np.asarray(rows, dtype=np.float64), np.asarray(labels), np.asarray(skills)


def train(train_sequences, validation_sequences, output):
    x, y, _ = features(train_sequences)
    xv, yv, _ = features(validation_sequences)
    ds = lgb.Dataset(x, label=y, feature_name=FEATURES, categorical_feature=["skill"])
    dv = lgb.Dataset(xv, label=yv, reference=ds)
    params = {
        "objective": "binary",
        "metric": "auc",
        "num_leaves": 15,
        "learning_rate": 0.04,
        "min_data_in_leaf": 80,
        "deterministic": True,
        "force_col_wise": True,
        "num_threads": 2,
        "seed": SEED,
        "verbosity": -1,
    }
    history = {}
    booster = lgb.train(
        params,
        ds,
        num_boost_round=300,
        valid_sets=[dv],
        valid_names=["validation"],
        callbacks=[
            lgb.early_stopping(25, verbose=False),
            lgb.record_evaluation(history),
        ],
    )
    booster.save_model(str(output))
    return {
        "best_iteration": booster.best_iteration,
        "params": params,
        "validation_auc": history["validation"]["auc"],
    }
