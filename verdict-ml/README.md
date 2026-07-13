# Verdict ML runtime

This package loads the PageVerdict and LinkVerdict models used by the crawler.

Training, labeling, evaluation, and model releases live in
[labeling-lab](https://github.com/julilili42/labeling-lab). Copy a tested
release into `artifacts/`:

- `page_verdict.joblib` and its metrics
- `link_verdict.joblib` and its metrics

The runtime must keep the feature builders in `page/features.py` and
`link/features.py` aligned with the training release.
