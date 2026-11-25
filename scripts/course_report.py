"""Build the English course submission from the published experiment records."""

import json
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/LumiRead_Business_and_ML.pdf"
FONT = Path(os.getenv("LUMIREAD_FONT_DIR", "/System/Library/Fonts/Supplemental"))
for name, suffix in [
    ("TNR", ""),
    ("TNR-B", " Bold"),
    ("TNR-I", " Italic"),
    ("TNR-BI", " Bold Italic"),
]:
    pdfmetrics.registerFont(TTFont(name, str(FONT / f"Times New Roman{suffix}.ttf")))
pdfmetrics.registerFontFamily(
    "TNR", normal="TNR", bold="TNR-B", italic="TNR-I", boldItalic="TNR-BI"
)

c = Canvas(
    str(OUT),
    pagesize=A4,
    initialFontName="TNR",
    initialFontSize=12,
    initialLeading=18,
)
c.setTitle("LumiRead | Business proposal and machine learning evaluation")
c.setAuthor("LumiRead project")
c.setCreator("LumiRead course report generator")
c.setSubject("Business proposal, desktop prototype and empirical model evaluation")
w, h = A4
margin = 2.54 * cm
width = w - 2 * margin
y = h - margin
ink = colors.HexColor("#172c24")
accent = colors.HexColor("#385a49")
rule = colors.HexColor("#aab7ab")
page = 0


def read(path):
    return json.loads((ROOT / path).read_text())


def draw_block(block, space):
    global y
    _, height = block.wrap(width, h)
    if y - height < margin - 0.01:
        raise ValueError(
            f"Page {page} overflows the bottom margin by {margin - y + height:.1f} pt"
        )
    block.drawOn(c, margin, y - height)
    y -= height + space


def paragraph(text, bold=False, space=10, hanging=False):
    style = ParagraphStyle(
        "text",
        fontName="TNR-B" if bold else "TNR",
        fontSize=12,
        leading=18,
        textColor=ink,
        leftIndent=36 if hanging else 0,
        firstLineIndent=-36 if hanging else 0,
    )
    draw_block(Paragraph(text, style), space)


def start(title):
    global page, y
    if page:
        c.showPage()
    page += 1
    y = h - margin
    c.setFillColor(accent)
    c.setFont("TNR", 12, 18)
    c.drawString(margin, y - 12, "GTSC2143     Machine Learning for Business")
    c.drawRightString(w - margin, y - 12, f"LumiRead     /     {page}")
    c.setStrokeColor(rule)
    c.setLineWidth(0.5)
    c.line(margin, y - 21, w - margin, y - 21)
    y -= 39
    paragraph(title, bold=True, space=13)


def section(title):
    paragraph(title, bold=True, space=3)


def picture(path, max_height):
    global y
    im = ImageReader(ROOT / path)
    iw, ih = im.getSize()
    scale = min(width / iw, max_height / ih)
    if y - ih * scale < margin:
        raise ValueError(f"Figure on page {page} exceeds the bottom margin")
    c.drawImage(
        im,
        margin + (width - iw * scale) / 2,
        y - ih * scale,
        iw * scale,
        ih * scale,
        mask="auto",
    )
    y -= ih * scale + 8


def table(rows, fractions):
    grid = Table(rows, colWidths=[width * part for part in fractions], hAlign="LEFT")
    grid.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "TNR", 12, 18),
                ("FONT", (0, 0), (-1, 0), "TNR-B", 12, 18),
                ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("LINEABOVE", (0, 0), (-1, 0), 0.6, rule),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, rule),
                ("LINEBELOW", (0, -1), (-1, -1), 0.6, rule),
            ]
        )
    )
    draw_block(grid, 11)


vision = read("reports/vision_evaluation.json")
ritw = read("artifacts/ritw/metrics.json")
replays = read("artifacts/ritw/replays.json")
example = next(r for r in replays["clips"] if r["id"] == replays["showcase"])
fed = read("artifacts/federated/report.json")
models = fed["comparison"]
choices = [
    ("Central DKT", "central_dkt"),
    ("FedAvg DKT", "federated_dkt"),
    ("LightGBM", "lightgbm"),
]
start("LumiRead | A family eye-care notebook")
paragraph(
    "A low light reading can be brief. A parent needs to know how long it lasted, where the sensor was worn and when the reading recovered. LumiRead replays those observations on an ordinary computer. A separate eye-tracking experiment estimates when reading takes place and which medium the wearer sees."
)
picture("apps/web/public/products/frame.webp", 150)
paragraph(
    "<i>Figure 1. Integrated frame concept.</i> The product showcase also includes a clip for existing prescription glasses."
)
section("The family decision")
paragraph(
    "Families with primary-school children could use a daily record to adjust a desk lamp, increase the distance to a screen or plan a break. The prototype detects reading and estimates the medium. It replays distance and light reminders, tracks study time, links advice to events and summarizes daily and weekly records."
)
paragraph(
    "Two independent adult studies supply the measured evidence. The reading model runs on Meta Project Aria recordings. The environmental rules use a Clouclip export. A labelled fictional week shows what a complete family report could look like. Usefulness and health outcomes in children require a separately designed study."
)

start("Reading recognition on Meta’s Seattle recordings")
paragraph(
    "Reading in the Wild includes purposeful reading, everyday tasks and scenes with visible text that the wearer is not reading. We fixed a panel from Meta’s published Seattle splits. Each split spans print, digital, object text, alternating reading, everyday non-reading and text-present non-reading. Within each group a stable hash ranks whole recordings. Each recording belongs to one split (Yang et al., 2025)."
)
section("Table 1. Valid decisions at one-second intervals")
table(
    [["Split", "Recordings", "Covered seconds"]]
    + [
        [
            label,
            str(ritw["splits"][k]["recordings"]),
            f"{ritw['splits'][k]['seconds']:,}",
        ]
        for k, label in [
            ("train", "Training"),
            ("val", "Validation"),
            ("test", "Held-out test"),
        ]
    ],
    [0.40, 0.26, 0.34],
)
paragraph(
    "We use the preceding two seconds of binocular gaze velocity and six-axis head velocity. We align each channel to device time and reject missing or stale windows. Meta’s frozen binary and four-class transformer checkpoints run on these two signals. The reference video provides a synchronized view for a presenter."
)
paragraph(
    "We independently fitted two class-balanced logistic regressions on the training split. Their 36 inputs summarize the mean, standard deviation, mean absolute and maximum absolute value of nine channels. Validation selected C = 0.1 for both tasks. The final comparison uses identical held-out windows."
)
paragraph(
    "For alternating tasks we use the separately annotated reading intervals. For other tasks we score within the published start and stop annotations. Missing windows appear as gaps. Recording IDs, file digests and all test predictions are available with the public reproduction code."
)

start("What the held-out predictions support")
section("Table 2. Detection, duration and false positives")
table(
    [["Method", "Reading F1", "Duration MAE", "Hard-negative FPR"]]
    + [
        [
            label,
            f"{ritw[k]['read_f1']:.3f}",
            f"{ritw[k]['duration_mae_seconds']:.1f} s",
            f"{ritw[k]['hard_false_positive_rate']:.1%}",
        ]
        for k, label in [
            ("official", "Meta checkpoints"),
            ("logistic", "Logistic baselines"),
        ]
    ],
    [0.31, 0.20, 0.22, 0.27],
)
paragraph(
    "F1 measures agreement on reading at the decision instant. Duration MAE is the mean absolute error per recording on the covered time. The hard-negative denominator is 939 seconds of text-present non-reading. Meta produced 142 false reading decisions in this group, compared with 501 for logistic regression."
)
section("Table 3. Four-class medium recall")
table(
    [["True class", "Test seconds", "Meta", "Logistic"]]
    + [
        [
            name,
            f"{ritw['official']['medium_support'][name]:,}",
            f"{ritw['official']['medium_recall'][name]:.1%}",
            f"{ritw['logistic']['medium_recall'][name]:.1%}",
        ]
        for name in replays["classes"]
    ],
    [0.32, 0.25, 0.2, 0.23],
)
paragraph(
    "The binary model detects reading more reliably than the medium model distinguishes print, screens and objects. The dashboard exposes uncertain media and keeps phone and computer distance scenarios under user control. These adult results do not establish accuracy for children."
)
paragraph(
    f"In the default alternating test recording, both motion streams cover {example['covered_seconds']} seconds. The reference contains {example['reference_read_seconds']:.1f} seconds of reading in that coverage. The detector identifies {example['predicted_read_seconds']} seconds. The timeline lets a presenter inspect individual disagreements."
)

start("Distance, lighting and recovery")
paragraph(
    "The Clouclip export contains 77,847 working-distance and worn-light readings from one adult graduate student. The export has nominal five-second rows. The device can refresh light more slowly. No task annotation identifies whether the person was reading a book, phone or computer. The presenter chooses a scenario and the server evaluates original timestamps (Zauner et al., 2026)."
)
section("Table 4. Reminders on 21 November 2020 in the paper scenario")
table(
    [
        ["Excerpt", "Samples", "Triggered", "Recovered"],
        ["Stable", "14", "None", "None"],
        ["Near distance", "11", "09:10:13", "09:10:28"],
        ["Dim light", "10", "09:45:27", "09:45:37"],
    ],
    [0.35, 0.17, 0.24, 0.24],
)
paragraph(
    "Distance below 33 cm for paper, 40 cm for a phone or 50 cm for a computer must persist for ten seconds. Worn light below 300 lux must persist for thirty seconds. Two consecutive valid readings at least 2 cm above the distance limit or at least 350 lux close the respective reminder. A missing reading or gap over five seconds interrupts a pending streak."
)
paragraph(
    "The mobile and computer distances and the average desktop illuminance reference come from WS/T 773–2020. The family guideline also advises about one Chinese foot of reading distance. A worn light sensor can suggest checking the work surface. A desktop lighting assessment requires a measurement on that surface. Persistence and recovery margins are engineering choices."
)
paragraph(
    "The three short replays show the original sample and source-file line at each alert. Changing playback speed changes elapsed classroom time. The recorded trigger and recovery timestamps stay fixed."
)

start("Study time, advice and the parent report")
section("When the clock advances")
paragraph(
    "A valid reading decision adds one second of activity. The timer can also record a manually started paper, writing or electronic session. It recommends a break at 40 minutes of study or 30 minutes of electronic learning. The 2018 eight-ministry guidance recommends distance viewing for about ten minutes after 30–40 minutes of electronic learning. We chose the early end for the demonstration."
)
paragraph(
    "Brief pauses suspend accrual. A continuous ten-minute interruption or a session end starts a new bout. An explicit ten-minute rest generates a completion event. The real RitW recordings are short, so a separate accelerated demonstration exercises both thresholds."
)
section("How a parent reads the week")
paragraph(
    "RitW reports aggregate test clips by recording start date in UTC. Multiple adults may contribute to a date. Clouclip reports use one adult’s local device date and count an alert on its trigger day. Coverage sums only valid adjacent observations. A blank day is shown as unknown."
)
paragraph(
    "The fictional student example runs from 16 to 22 November. It contains 268 minutes of paper study and 193 minutes of electronic study. Applying the same rules yields eight distance, four light and six rest reminders. A parent can open each day, examine the event time, and see advice about lighting, viewing distance or rest. The pattern was constructed to demonstrate a weekly report."
)
section("Conditions for a family pilot")
paragraph(
    "Seek appropriate permission and test reminder accuracy, false alarms, comfort and whether parents act on advice. Meta’s Seattle data and models carry a noncommercial license. A commercial pilot needs appropriate rights and evidence on its own hardware."
)

start("Commercial assumptions and the observed cost of grading")
paragraph(
    "The team proposes CNY 799 for integrated frames, CNY 499 for a 13 g clip and CNY 198 annually for family grading and guided practice. At an estimated CNY 349 in frame parts, CNY 450 remains, or 56.3% of the sticker price. Assembly, freight, retailer discounts, returns and warranty determine how much remains as gross profit. The clip still needs a bill of materials (LumiRead Project, 2026a)."
)
section("Subscription sensitivity")
paragraph(
    "At 55% initial paid take-up and 78% annual retention, three years of expected subscription revenue per hardware buyer equal CNY 260.10, calculated as 198 × 0.55 × (1 + 0.78 + 0.78²). At 30% take-up, the estimate falls to CNY 141.87. Both assume fixed pricing, one subscription per converted buyer, no reactivation and no discounting. The pilot must establish actual retention and acquisition cost (LumiRead Project, 2026a)."
)
section("Historical cost of the optional grading service")
paragraph(
    "The earlier course evaluation reported a mean estimated USD 0.00997 per typeset page and a median processing time of 9.23 seconds across 24 jobs. Nine historical phone photographs averaged USD 0.01287 and had a median of 7.50 seconds. At the earlier rate, 200 similar typeset pages would cost about USD 1.99 before hosting, support and taxes (LumiRead Project, 2026b)."
)
section("Desktop presentation")
paragraph(
    "Open the eye-care notebook first. Compare a real recording with its reading labels, play the dim-light excerpt, advance an electronic session to its break, and inspect a dated report. The optional product and learning appendices can be opened separately. Frozen predictions and the sensor export run locally. A presenter can add the licensed preview through Meta’s official download form."
)

start("Appendix A | Family accounts and homework practice")
section("How the three notebooks start")
paragraph(
    "The local app offers three demonstration identities. A begins with a short history, B with sustained practice in one skill and C with a longer history covering several skills. Selection rules were fixed before choosing three distinct validation learners. The rules use history length, skill distribution and a stable hash. Each account retains its source order. The file contains response durations but lacks dates for individual answers, so the app displays the original order identifier where a date is unavailable (ASSISTments, 2009–2010; LumiRead Project, 2026b)."
)
section("What happens after a parent uploads a worksheet")
paragraph(
    "A parent uploads a normal image in B. The local server rotates it, strips embedded metadata, hashes the retained image and enqueues a grading job. An online provider returns the transcription, verdict, hints and an explanation for each problem. The notebook can retrieve updates after a refresh. One supplied pair of worksheets keeps 8 + 7 = 15 unchanged and changes the answer for 9 − 4 from 8 to 5. Each upload has its own image and job record (DeepSeek, 2026; LumiRead Project, 2026b; OpenAI, 2026)."
)
paragraph(
    "The parent can compare a verdict with the original, reveal the fawn guide’s hints one at a time, and save an item. A saved item is a bookmark. A versioned correction replaces one learning observation and retains the original provider result. A pending item enters the history when resolved. A retry reuses its submission identifier. These distinctions keep the per-skill evidence counts interpretable (LumiRead Project, 2026b)."
)
paragraph(
    "The frozen central LSTM recomputes six next-answer probabilities locally. The notebook presents each probability beside its supporting count and proposes one exercise for each of the two lowest predicted skills. Submitting and grading a new practice answer adds one attempt. Switching accounts changes the accessible uploads, archive, recommendations and history. Resetting an account restores its source history (LumiRead Project, 2026b)."
)

start("Online worksheet evaluation on ordinary screenshots")
paragraph(
    "We generated 24 typeset pages with five problems each and a precomputed arithmetic key. Six categories each contributed 20 items. Problems included arithmetic, fractions, decimals, equations, area and word-problem modelling. All 24 screenshots went through the regular file-upload endpoint to the live OpenAI provider. Each receipt identifies the input image, job, provider request, model, latency and usage (LumiRead Project, 2026b)."
)
paragraph(
    f"The grader returned automatic verdicts for {vision['automatic']} of {vision['labelled']} items ({vision['coverage']:.1%} coverage) and agreed with the key on {vision['agreed']} ({vision['agreement']:.2%} agreement). There were {vision['unmatched_predictions']} unmatched predictions. On page 19, question 5 asked for the area of an 8 cm × 5 cm rectangle. The provider transcribed the correct answer, 40, and marked it incorrect. A family needs access to the original and to the verdict-review control even when the transcription looks right (LumiRead Project, 2026b)."
)
paragraph(
    "The screenshots repeat six question templates, use clean typesetting and insert 999 for deliberately wrong answers. Coverage is the proportion of reference items automatically graded. Agreement divides matching verdicts by automatic grades and unmatched extra predictions. Estimating accuracy on handwriting, unusual layouts, plausible child errors and unseen problem types requires independently labelled household pages (LumiRead Project, 2026b)."
)
section("Earlier physical evidence")
paragraph(
    "A separate iPhone check used two real photographs with a changed handwritten answer, different file digests and two provider request IDs. The parent viewed each result twice. Two ten-trial field runs missed every gesture upload. The subsequent touch control produced five same-side double-tap photographs, each with a live grading result. Physical single-tap and quiet-mode controls remained open. Separately, OpenAI and DeepSeek each returned the expected answers on a two-item provider smoke test. None of these trials contribute to the screenshot agreement denominator (LumiRead Project, 2026b)."
)

start("Appendix B | Knowledge tracing on held-out learners")
paragraph(
    "We retained 44,212 first-attempt answers across 2,362 learners from the corrected, non-collapsed ASSISTments Skill Builder file. The pipeline maps explicit source tags to six skills, merges duplicate tags for one answer and excludes automatically scored open responses. Whole learners belong to training (1,653), validation (354) or test (355). Chronological source order keeps later answers out of each prediction (ASSISTments, 2009–2010; Feng et al., 2009; LumiRead Project, 2026b)."
)
paragraph(
    "The central DKT uses a 12-dimensional embedding and a 24-unit LSTM. Starting from a shared first-question state, it encodes earlier skill and correctness pairs and predicts a probability for each next skill. Training ran on an RTX 4080 SUPER. LightGBM uses the same targets with earlier counts, accuracy and recency. The family notebook runs the frozen central weights on its CPU (Ke et al., 2017; LumiRead Project, 2026b; Piech et al., 2015)."
)
section("Table B1. Results on 6,694 first attempts from 355 held-out learners")
score_rows = [["Model", "ROC AUC", "Accuracy", "F1", "Brier", "Short AUC"]]
for label, key in choices:
    m = models[key]["overall"]
    score_rows.append(
        [
            label,
            f"{m['auc']:.4f}",
            f"{m['accuracy']:.4f}",
            f"{m['f1']:.4f}",
            f"{m['brier']:.4f}",
            f"{models[key]['short_history']['auc']:.4f}",
        ]
    )
table(score_rows, [0.23, 0.16, 0.16, 0.13, 0.14, 0.18])
paragraph(
    "Short AUC covers the 1,519 target answers with zero to four earlier mapped attempts. ROC AUC evaluates ranking. Brier measures squared probability error and favours lower values. F1 and accuracy use a 0.50 threshold, with correct as the positive class. LightGBM led on AUC and Brier. FedAvg had higher recall for correct responses and the highest F1 at this threshold (LumiRead Project, 2026b)."
)
paragraph(
    "Each profile estimates correctness on the next related question. A short history leaves little individual evidence, particularly when a skill has no previous observations. Asking for a hint is scored as incorrect, and the platform’s practice-until-correct rule affects which answers are observed. Calibration on Chinese primary-school homework and effects on subsequent learning remain open (ASSISTments, 2009–2010; Feng et al., 2009; LumiRead Project, 2026b)."
)

start("Federated learning experiment and reproducibility")
paragraph(
    "One training learner represents one simulated client. In each round, 64 sampled clients start from the same global model and train on their own sequences for three SGD epochs. The server averages their parameters in proportion to valid prediction targets. The first answer contributes one target and padding contributes zero. The pre-specified learning rate was 0.30 and the gradient norm on each client was clipped to 5 (LumiRead Project, 2026b; McMahan et al., 2017)."
)
section("Table B2. Validation selection and final testing")
table(
    [["Seed", "Selected round", "Validation AUC", "Test AUC"]]
    + [
        [
            str(r["seed"]),
            str(r["best_round"]),
            f"{r['best_validation_auc']:.4f}",
            f"{r['test']['auc']:.4f}",
        ]
        for r in fed["runs"]
    ],
    [0.20, 0.26, 0.32, 0.22],
)
selected = fed["selected"]
run = next(r for r in fed["runs"] if r["seed"] == selected["seed"])
row = run["rounds"][selected["round"] - 1]
summary = fed["three_seed_test_summary"]["auc"]
paragraph(
    f"Three fixed seeds each ran for 60 rounds. The highest validation AUC chose each checkpoint and then the default seed. The selected round had {row['client_count']} clients and {row['target_count']:,} training targets. Across the three seeds, held-out ROC AUC averaged {summary['mean']:.4f} (sample SD {summary['sample_std']:.4f}). Under this budget the centrally trained LSTM ranked responses better on the same test students (LumiRead Project, 2026b)."
)
paragraph(
    f"The independent training viewer lets a presenter select a seed and round, inspect loss, client counts and validation metrics, and replay the frozen curves. At round {row['round']}, a full FP32 parameter vector per client implies {row['logical_upload_bytes']:,} bytes up and {row['logical_download_bytes']:,} bytes down. These are logical volumes for a single-computer simulation. There was no physical network measurement, secure aggregation or differential-privacy mechanism (LumiRead Project, 2026b; McMahan et al., 2017)."
)
paragraph(
    "A second complete three-seed run reproduced all 180 client selections and validation metrics and the exported weights. Standard-library CPU inference on all 6,694 federated test prefixes differed from PyTorch by at most 0.000000100. For the separate central model, 30 CPU outputs matched the CUDA reference within 0.00003781. Receiving researchers reconstruct individual learning histories locally from the pinned source and verify file digests (ASSISTments, 2009–2010; LumiRead Project, 2026b)."
)


def reference(title, url=""):
    content = title + (f' <a color="#355b48" href="{url}">{url}</a>' if url else "")
    paragraph(content, hanging=True, space=10)


start("References | Eye care")
reference(
    "Yang, C., Alam, S., Siam, S. I., Proulx, M., Mathias, L., Somasundaram, K., Pesqueira, L., Fort, J., Sheriffdeen, S., Parkhi, O., Ren, C., Zhang, M., Chai, Y., Newcombe, R., &amp; Kim, H. J. (2025). Reading Recognition in the Wild. <i>Advances in Neural Information Processing Systems</i>.",
    "https://arxiv.org/abs/2505.24848",
)
reference(
    "Meta. (2025). <i>Reading in the Wild, Seattle dataset and models</i>. CC BY-NC 4.0. LumiRead selected the recordings, aligned signals, trained the baselines and produced the evaluated timelines.",
    "https://github.com/facebookresearch/reading_in_the_wild",
)
reference(
    "Ministry of Education of China and seven other departments. (2018). <i>Comprehensive plan for the prevention and control of myopia in children and adolescents</i>.",
    "https://www.moe.gov.cn/srcsite/A17/moe_943/s3285/201808/t20180830_346672.html",
)
reference(
    "National Health Commission of China. (2020). <i>WS/T 773–2020. Hygienic requirements for using video displays in online learning by primary and secondary school students</i>.",
    "https://www.nhc.gov.cn/fzs/c100048/202008/d42388863f2340c4a3ca880b3e6b2c50/files/1733125825170_45982.pdf",
)
reference(
    "Zauner, J., Nicholls, A., Ostrin, L. A., &amp; Spitschan, M. (2026). Analysis of human visual experience data. <i>Journal of Vision, 26</i>(7), Article 1.",
    "https://doi.org/10.1167/jov.26.7.1",
)
start("References | Business and learning")
reference(
    "ASSISTments. (2009–2010). <i>2009–2010 ASSISTment data: Skill builder, corrected release</i> [Data set].",
    "https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data/skill-builder-data-2009-2010",
)
reference(
    "Buryi, A. (2026). <i>A controlled smartphone image dataset for AI-based workplace illuminance estimation</i> [Data set]. Zenodo.",
    "https://doi.org/10.5281/zenodo.20657011",
)
reference(
    "DeepSeek. (2026). <i>Vision and image inputs</i>.",
    "https://api-docs.deepseek.com/guides/vision/",
)
reference(
    "Feng, M., Heffernan, N. T., &amp; Koedinger, K. R. (2009). Addressing the assessment challenge with an online system that tutors as it assesses. <i>User Modeling and User-Adapted Interaction, 19</i>, 243–266.",
    "https://doi.org/10.1007/s11257-009-9063-7",
)
reference(
    "Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q., &amp; Liu, T.-Y. (2017). LightGBM: A highly efficient gradient boosting decision tree. <i>Advances in Neural Information Processing Systems, 30</i>.",
    "https://proceedings.neurips.cc/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html",
)
reference(
    "LumiRead Project. (2026a). <i>LumiRead MVP team execution proposal</i> [Internal business and product brief]. Course project materials."
)
start("References (continued)")
reference(
    "LumiRead Project. (2026b). <i>Technical implementation and evaluation records for LumiRead</i> [Software, datasets and experiment logs]. Course submission. The source guides are data/dkt/README.md and data/clouclip/README.md. Grading evidence is in reports/vision_evaluation.json, reports/desktop_vision_receipts.json and reports/iphone_evidence.json. The model card and experiment records are in docs/MODEL_CARD.md, artifacts/dkt and artifacts/federated."
)
reference(
    "McMahan, B., Moore, E., Ramage, D., Hampson, S., &amp; Agüera y Arcas, B. (2017). Communication-efficient learning of deep networks from decentralized data. In A. Singh &amp; J. Zhu (Eds.), <i>Proceedings of the 20th International Conference on Artificial Intelligence and Statistics</i> (Vol. 54, pp. 1273–1282). PMLR.",
    "https://proceedings.mlr.press/v54/mcmahan17a.html",
)
reference(
    "OpenAI. (2026). <i>GPT-6.2 Sol model and Standard pricing</i>.",
    "https://developers.openai.com/api/docs/models/gpt-6.2-sol",
)
reference(
    "Piech, C., Bassen, J., Huang, J., Ganguli, S., Sahami, M., Guibas, L. J., &amp; Sohl-Dickstein, J. (2015). Deep knowledge tracing. <i>Advances in Neural Information Processing Systems, 28</i>.",
    "https://papers.nips.cc/paper/5654-deep-knowledge-tracing",
)
c.save()
print(OUT)
