# ASSISTments 2009–2010 Skill Builder

LumiRead uses the **corrected, non-collapsed** archive hosted by the University of Science and Technology of China. The original project documents the 2009–2010 cohort and its corrections. Its currently linked corrected download collapses multiple skill labels into one row. The USTC file retains one row per skill tag, so its bytes and row count differ from that file. The pipeline groups mapped tags by answer event. [Official corrected release](https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data/skill-builder-data-2009-2010) · [USTC archive used](https://base.ustc.edu.cn/data/ASSISTment/2009_skill_builder_data_corrected.zip)

The archive contains `skill_builder_data_corrected.csv`. Its ZIP SHA-256 is `10c4fa76ae9410d8577cf9604cf21f8eed029552717a4b281d64945cf44ebe46`. The original data dictionary identifies `order_id` as chronological, `original=1` as a main problem, and `correct` as correctness on the first attempt. Asking for help is recorded as incorrect. Open-ended responses can be scored correct automatically. [Official data dictionary](https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data)

## Permissions and citation

The historical dataset page describes free use and requests citation of the exact release and the ASSISTments system paper. The eTrials terms give researchers access for their stated analysis, require protecting student anonymity and direct recipients to obtain the data independently. No open redistribution licence is published for these student-level logs. Raw ZIPs, student assignments and individual response sequences stay under the local `.cache/dkt/` directory. The distributable reconstruction inputs are the pinned URL and digest, the skill mapping, the split algorithm and aggregates. The reference input histories in `artifacts/dkt/parity.json` are authored test vectors. [eTrials data terms](https://www.etrialstestbed.org/data-sets) · [Official dataset citation instructions](https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data/skill-builder-data-2009-2010)

Citation requested by the publisher: Feng, M., Heffernan, N. T., & Koedinger, K. R. (2009). Addressing the assessment challenge with an online system that tutors as it assesses. *User Modeling and User-Adapted Interaction, 19*, 243–266. [Publisher](https://doi.org/10.1007/s11257-009-9063-7)

## Rebuilding the inputs

From the repository root, run `make -f ml/dkt/Makefile prepare`. An existing matching ZIP enables offline reconstruction. To seed the cache manually, place the exact archive at `.cache/dkt/assistments2009.zip`. The program verifies its digest, rebuilds the three splits and compares their row counts and sequence digests against the published summary.

1. Retain main problems with one of the exact source labels in the skill mapping. Exclude automatically correct open responses and all unmapped targets.
2. Group eligible labels by `(user_id, order_id)`. Verify the grouped problem and correctness agree. A mapped event with multiple distinct LumiRead skills is skipped. This release yielded zero such conflicts. An unmapped secondary source tag does not create another response.
3. Sort each learner's events by integer `order_id`. Distinct attempts on a repeated item keep their original positions. This dataset supplies order, without a wall-clock timestamp for each event.
4. Rank distinct learner identifiers by the SHA-256 of UTF-8 `assist09:6083:<user_id>`. Cut the ranked list at floor(0.70 × N) and floor(0.85 × N). Each learner and all of their events occur in exactly one split. Single-response learners contribute one cold-start target.
5. Write local JSONL rows as `[student_id, [[order_id, skill_index, correct], ...]]`. Both models verify and consume the same split files. The source records 401,756 tag rows and retains 44,212 eligible main-question events across 2,362 learners.

The mapping file gives the exact original tags with a rationale for each category. The summary records source tag counts, correct counts and unique event totals for every split and skill. [Skill mapping](skill_mapping.json) · [Counts and split digests](summary.json)

## Local demo histories

The frozen selection rules define three distinct, genuine learners. The selector prefers validation learners and considers test learners only if there is no match in the validation split. It never draws from training. The selection algorithm reads the number and categories of earlier problems without inspecting answers or model scores. Imported events retain the original numeric problem log order. Inspection of the fixed CSV header found only response-duration columns. Each event's wall-clock time is null. [Selection rules](demo_selection.json)

`make -f ml/dkt/Makefile demo-accounts` downloads the pinned archive if needed, reconstructs and verifies the split, and creates `data/dkt/demo_accounts.json` for local use. It uses only the Python standard library. For an existing copy of the exact ZIP, set `ARCHIVE=/path/to/assistments2009.zip`. The USTC mirror supplies the frozen non-collapsed corrected file. The current corrected link on the official project page points to a separately collapsed release. The archive digest distinguishes these versions. `make -f ml/dkt/Makefile check-demo-accounts` independently regenerates the selection and checks every local event.

The generated JSON includes individual response histories and must stay on the recipient’s machine under the source terms. It is excluded from version control. Packages may include the generator, aggregate metrics, source links and selection rules. Each recipient obtains the dataset independently. [eTrials terms](https://www.etrialstestbed.org/data-sets)
