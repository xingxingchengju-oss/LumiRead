# Reading recognition on RitW Seattle

LumiRead compares Meta's released `v1_default` reading detector and `v1_medium` four-class classifier with two locally trained logistic regressions. The original gaze/head experiment publishes predictions for 30 held-out recordings. The desktop reading monitor serves two validation replays with calibrated RGB review. A separate Clouclip study supplies the distance and illuminance readings.

## Reproduce the experiment

Use Python 3.11 and Git. After `make bootstrap`, follow the Seattle access form and obtain the Explorer JSON with the MPS assets for the Seattle subset as well as RGB previews and VRS archives for the monitor panel. The signed links expire after 14 days. Keep the manifest on your own computer. [Meta data explorer](https://explorer.projectaria.com/ritw) · [Download documentation](https://github.com/facebookresearch/reading_in_the_wild/tree/cb315554cf54927b9ca6056143bca96191afc98d/reading_in_the_wild_seattle)

```sh
make ritw-check
make ritw-preview MANIFEST=/absolute/path/to/ritw_download_urls.json
make ritw-setup
make ritw-fetch MANIFEST=/absolute/path/to/ritw_download_urls.json
make ritw-evaluate OUT=.cache/ritw/reproduced
diff artifacts/ritw/metrics.json .cache/ritw/reproduced/metrics.json
diff artifacts/ritw/replays.json .cache/ritw/reproduced/replays.json
```

The first command audits the published digests, recalculates the scores from the timelines and checks reminder boundaries. The second downloads the two classroom MP4s listed in the published monitor manifest. The last four commands reproduce training and evaluation from the official channels. Allow about 10 GB for the inputs plus space for the Python environment. The fetcher reads ZIP ranges, verifies the CRC of each extracted member and validates the MP4 against the manifest SHA-1. The metrics file lists the SHA-256 of each gaze file, each odometry file and both checkpoints. Local input, weights and preview reside under `.cache/ritw`. The normal web application only needs the frozen JSON. [Frozen artifacts and digests](../../artifacts/ritw)

## Offline RGB monitor

After `make bootstrap`, run `make ritw-preview MANIFEST=/absolute/path/to/ritw_download_urls.json` to prepare a classroom laptop. The browser reads the two local MP4s and the committed monitor data. It needs no external service during playback.

To reproduce the multimodal evaluation, obtain the Seattle Explorer manifest with RGB, MPS and VRS assets and run the commands below. The review stage uses the configured OpenAI vision account to process four RGB frames and their calibrated gaze positions per requested burst. It caches the structured evidence and provider receipt for each burst locally. The cache key includes the images, gaze, model, prompt and schema. Reusing this cache reproduces a frozen run. A fresh API run can yield different predictions.

```sh
make ritw-monitor-setup
make ritw-monitor-fetch MANIFEST=/absolute/path/to/ritw_download_urls.json
make ritw-monitor-frames
make ritw-monitor-review
make ritw-monitor-evaluate OUT=.cache/ritw/monitor-reproduced
```

The frozen v1_default checkpoint supplies a binary vote for each valid second. Each non-overlapping seven-second patch is anchored to the original video clock. The first and last patches use the available complete seconds. The first patch, a transition, a gap, tied or close votes (margin one), or 28 seconds since the last scheduled review triggers a burst. Inconclusive evidence is reviewed again. The original VRS description supplies each device’s factory calibration. Project Aria Tools applies the canonical RGB stream rescaling. The calibrated binocular ray at measured depth is transformed from CPF to RGB and rotated into the upright Seattle preview. Samples more than 50 ms from the frame, projected points outside the camera, and seconds without a valid vote remain unavailable.

The four frames span up to 1.8 seconds inside one patch. The reviewer receives no recording name, reference labels or vote counts. Matching the gaze against returned object boxes in at least two tiles confirms a medium. Strong screen/video evidence can resolve a gaze model reading vote as video, including subtitles. A strong vote contradicting visual rest or reading yields unknown. A clear reading vote with unresolved medium still contributes reading time. Each completed group of six eligible seconds settles exact ticks at the rate of each second’s winning patch label. The integer denominator is 504 ticks per point.

**Validation selection.** The task-16 validation candidates have a single official print or digital tag, a reading interval of at least seven seconds and an internal non-reading interval of at least twelve seconds. Their reading intervals supply reading references. Original RGB and calibrated gaze were inspected at one-second intervals to identify device type and independent rest excerpts. Uncertain excerpts are left unlabelled. Each candidate must have a score rise during annotated reading and a fall during a verified rest excerpt. Rank by mean reading/rest recall, reading-medium accuracy, undetermined fraction and recording ID. Both replays start at their first reviewed, correctly identified reading patch and preserve the original source clock. [Independent reference excerpts](monitor-reference.json)

**Held-out assessment.** The evaluation covers all eight official test recordings with `mode=Videos` and one deterministic phone-text, computer-text, print, object-text and non-reading control each. The original `reading=True` remains in the report. The product reference for the task window is video. The two records marked `Screen` also carry the explicit `Desktop` device tag. The non-reading control is a culinary task. Per-class denominators include every complete task second, even those with missing inputs or undetermined predictions. Medium recall is evaluated independently on recordings with a reference material or device. The report includes recording counts, second counts, abstentions and the predicted runs used to recompute the tables. [Held-out results and simulated score check](../../artifacts/ritw/monitor-metrics.json)

## Panel and targets

The pinned upstream commit is `cb315554cf54927b9ca6056143bca96191afc98d`. Keep each Seattle recording in its published split. Eligible recordings have a successful calibration and either the task-16 interval annotations or both Whisper task boundaries. Within each split, rank recording IDs by SHA-256 of `LumiRead-Seattle-v1/` followed by the ID. Take 8 training, 3 validation and 5 test recordings from each of six groups. The groups are print, digital, text on objects, alternating reading, everyday non-reading and text-present non-reading (tasks 8–10). This fixed, deliberately balanced panel has a different task distribution from natural household use.

| Split | Recordings | Valid one-second decisions |
| --- | ---: | ---: |
| Train | 48 | 8,258 |
| Validation | 18 | 3,267 |
| Test | 30 | 5,874 |

For single-task recordings the scoreable interval lies between `whisper_start` and `whisper_end`. Task 16 uses the calibration boundary, final boundary and individual reading intervals in `task16_annotations.csv`. The medium for mixed tasks comes from unambiguous material tags. An ambiguous reading medium is omitted from the four-class loss and recall denominator. Non-reading counts as its own class. The hard-negative metric covers the five sampled task-8–10 test recordings. [Annotation definitions](https://github.com/facebookresearch/reading_in_the_wild/tree/cb315554cf54927b9ca6056143bca96191afc98d/reading_in_the_wild_seattle)

## Timing and models

The paired calibration timestamp and its video offset align the MPS tracking clock with video seconds. At each integer second we take the latest 121 gaze samples ending at or before that instant. We form the normalized binocular direction in the central pupil frame, difference it at nominal 60 Hz, and align six velocity channels from open-loop odometry to the latest preceding sample at each gaze timestamp. A two-second window must span 1.9–2.1 seconds, have strictly increasing gaze timestamps, finite inputs, and sample gaps or alignment delays below 50 ms. Each valid prediction describes one second until the next integer boundary. Missing windows appear as gaps. RGB is used for visual playback only.

The released transformers consume the same 120-step inputs as the baselines. The medium checkpoint includes an unused RGB position embedding, which is dropped before strict loading of the gaze and head model. The binary decision and four-way medium decision are independent. The dashboard counts a medium only during a predicted reading second. If the medium classifier predicts non-reading then, the report counts the medium as unknown.

The logistic models use the mean, population standard deviation, mean absolute value and largest absolute value of each of nine channels. Each training-only scaler and class-balanced classifier uses 36 features. Binary F1 and four-class macro F1 on validation choose C independently from 0.1, 1 and 10. Both selected 0.1. The baseline JSON stores the channel order, scaler and coefficients. For the binary model, a positive linear score selects the second class. For the four-way model, select the class with the highest score.

## Held-out results

| Method | Reading F1 | Precision | Recall | Duration MAE per recording | Text-present non-reading false positives |
| --- | ---: | ---: | ---: | ---: | ---: |
| Meta checkpoints | 0.782 | 87.4% | 70.8% | 35.4 s | 142 / 939 (15.1%) |
| Logistic baselines | 0.694 | 61.2% | 80.2% | 59.4 s | 501 / 939 (53.4%) |

| True medium | Test seconds | Meta recall | Logistic recall |
| --- | ---: | ---: | ---: |
| No read | 3,053 | 82.0% | 38.8% |
| Print | 783 | 22.6% | 34.1% |
| Digital | 1,502 | 28.0% | 23.6% |
| Object | 536 | 26.5% | 45.7% |

F1 compares the binary decision with the label at the decision instant. Duration error compares predicted reading seconds with the exact annotated reading time overlapping covered seconds, then averages absolute errors across the 30 sequences. Repeated decisions within a sequence are correlated. The metrics describe a small adult panel. Media-specific recall is low and child performance and health outcomes require separate evaluation. The dashboard uses manually chosen phone and computer distance scenarios.

## Attribution and use

Charig Yang, Samiul Alam, Shakhrul Iman Siam, Michael Proulx, Lambert Mathias, Kiran Somasundaram, Luis Pesqueira, James Fort, Sheroze Sheriffdeen, Omkar Parkhi, Carl Ren, Mi Zhang, Yuning Chai, Richard Newcombe and Hyo Jin Kim. *Reading Recognition in the Wild*, NeurIPS 2025. Meta distributes the Seattle data and reference models under CC BY-NC 4.0. The published reference intervals and derived artifacts in `artifacts/ritw` carry this attribution and noncommercial license. LumiRead selected a subset, aligned the channels, trained baselines and computed the metrics and timelines. A commercial product needs appropriate rights to its training and inference assets. [Paper](https://arxiv.org/abs/2505.24848) · [Pinned upstream source and license](https://github.com/facebookresearch/reading_in_the_wild/tree/cb315554cf54927b9ca6056143bca96191afc98d) · [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)
