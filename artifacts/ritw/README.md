# LumiRead evaluation of Reading in the Wild

`metrics.json` contains the split inventory, input and checkpoint hashes, validation selection and held-out results. `replays.json` contains the binding to the classroom preview, reference intervals and predictions on the original video clock. A prediction run is `[start_second, end_second_exclusive, reading_class, medium_class]`. `baselines.json` stores both fitted logistic models.

These artifacts derive from **Reading Recognition in the Wild**, Charig Yang et al., NeurIPS 2025, Meta's Seattle subset. Released here under **CC BY-NC 4.0**. The linked experiment guide records the transformations, author list, sources and reproduction commands. [Experiment guide](../../ml/ritw/README.md) · [Meta release](https://github.com/facebookresearch/reading_in_the_wild) · [License](https://creativecommons.org/licenses/by-nc/4.0/)
