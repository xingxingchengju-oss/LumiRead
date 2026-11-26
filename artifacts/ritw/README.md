# LumiRead evaluation of Reading in the Wild

`metrics.json` contains the split inventory, input and checkpoint hashes, validation selection and held-out results. `replays.json` contains the binding to the classroom preview, reference intervals and predictions on the original video clock. A prediction run is `[start_second, end_second_exclusive, reading_class, medium_class]`. `baselines.json` stores both fitted logistic models.

`monitor.json` contains the two classroom replays, their patch decisions and frame-level evidence, source-clock score snapshots and reminder instants. `monitor-metrics.json` contains the validation ranking, held-out reference labels and predictions, per-class recall and the explicitly simulated 41-minute score check. Licensed RGB previews are fetched separately with `make ritw-preview`.

The [parent weekly report](parent-weekly.zh.v2.json) contains a published Chinese summary, two suggestions and their fact IDs. The backend assembles seven fictional dates from the original seconds of the two classroom replays and the 13 test prediction timelines. The publication records the text model and hashes of the aggregate input, frozen prompt, output schema and provider receipt. [Frozen prompt](../../apps/api/prompts/parent-weekly.zh.v2.txt)

These artifacts derive from **Reading Recognition in the Wild**, Charig Yang et al., NeurIPS 2025, Meta's Seattle subset. Released here under **CC BY-NC 4.0**. The linked experiment guide records the transformations, author list, sources and reproduction commands. [Experiment guide](../../ml/ritw/README.md) · [Meta release](https://github.com/facebookresearch/reading_in_the_wild) · [License](https://creativecommons.org/licenses/by-nc/4.0/)
