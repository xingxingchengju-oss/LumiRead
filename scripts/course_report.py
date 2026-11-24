"""Build the English course submission from the published experiment records."""

import json
import os
from collections import Counter
from pathlib import Path
from statistics import mean, median

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
receipts = read("reports/desktop_vision_receipts.json")["pages"]
phone = read("reports/iphone_evidence.json")
fed = read("artifacts/federated/report.json")
models = fed["comparison"]
choices = [
    ("Central DKT", "central_dkt"),
    ("FedAvg DKT", "federated_dkt"),
    ("LightGBM", "lightgbm"),
]
confusion = Counter(
    (item["expected"], item["observed"])
    for receipt in receipts
    for item in receipt["items"]
)
if (
    len(receipts) != vision["pages"]
    or sum(confusion.values()) != vision["labelled"]
    or sum(n for (a, b), n in confusion.items() if a == b) != vision["agreed"]
):
    raise ValueError(
        "The screenshot evaluation totals differ from the saved online receipts."
    )
desktop_cost = mean(r["estimated_usd"] for r in receipts)
desktop_latency = median(r["seconds"] for r in receipts)

start("LumiRead | Business proposal and machine learning evaluation")
paragraph(
    "A child writes 8 for 9 minus 4. What would help a parent more than a red mark? LumiRead shows the original answer, explains the subtraction one step at a time and offers a new problem. The child can continue working on paper. The desktop demonstration follows that decision from the worksheet to the next practice response (LumiRead Project, 2026a, 2026b)."
)
picture("apps/web/public/products/frame.webp", 160)
paragraph(
    "<i>Figure 1. Integrated frame concept.</i> A clip for existing prescription glasses provides a second proposed form factor. Both can be rotated and inspected in the product showcase (LumiRead Project, 2026a, 2026b)."
)
section("Customers and distribution")
paragraph(
    "The proposed customers are families of children aged 6–12 who already use paper homework. Parents can decide when to respond to study conditions and what to practise after a mistake. An optical-store pilot would reach families choosing a new frame or keeping an existing prescription. It could measure fitting time, comfort, returns and subscription take-up before the team commits to production (LumiRead Project, 2026a)."
)
paragraph(
    "The working notebook, sensor replay and model comparisons run on an ordinary computer. A new worksheet uses an online grading service. The eyewear remains a design concept. The course evidence measures prediction quality, reminder logic and grading on defined inputs. A longitudinal trial would be needed to measure the effect on learning or vision (LumiRead Project, 2026a, 2026b)."
)

start("Commercial assumptions and the observed cost of grading")
paragraph(
    "The team proposes CNY 799 for integrated frames, CNY 499 for a 13 g clip and CNY 198 annually for family grading and guided practice. At an estimated CNY 349 in frame parts, CNY 450 remains, or 56.3% of the sticker price. Assembly, freight, retailer discounts, returns and warranty determine how much remains as gross profit. The clip still needs a bill of materials (LumiRead Project, 2026a)."
)
section("Subscription sensitivity")
paragraph(
    "At 55% initial paid take-up and 78% annual retention, three years of expected subscription revenue per hardware buyer equal CNY 260.10, calculated as 198 × 0.55 × (1 + 0.78 + 0.78²). At 30% take-up, the estimate falls to CNY 141.87. Both assume fixed pricing, one subscription per converted buyer, no reactivation and no discounting. The pilot must establish actual retention and acquisition cost (LumiRead Project, 2026a)."
)
section("Table 1. Grading price estimates from two separate workloads")
table(
    [
        ["Input and workload", "Pages", "Median time", "Mean USD/page"],
        [
            "Desktop typeset screenshots",
            str(len(receipts)),
            f"{desktop_latency:.2f} s",
            f"{desktop_cost:.5f}",
        ],
        [
            "Historical iPhone photos",
            str(len(phone["captured_pages"])),
            f"{phone['median_seconds']:.2f} s",
            f"{phone['mean_standard_usd']:.5f}",
        ],
    ],
    [0.43, 0.09, 0.22, 0.26],
)
paragraph(
    f"The estimates apply the recorded Standard rate card to token usage, including cache reads, cache writes and output. The {len(receipts)} screenshot jobs totalled USD {sum(r['estimated_usd'] for r in receipts):.5f}. Processing time runs from worker claim to job completion. Elapsed time and prices depend on the workload and service configuration (LumiRead Project, 2026b; OpenAI, 2026)."
)
paragraph(
    f"At 200 similar screenshot pages per year, expected grading charges would be about USD {200 * desktop_cost:.2f} per subscribed household. Hosting, support, retries without receipts, taxes and currency conversion are additional costs. Net subscription contribution also depends on channel terms and the number of pages families actually submit (LumiRead Project, 2026a, 2026b; OpenAI, 2026)."
)

start("From an isolated family account to a new practice answer")
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
section("Table 2. Screenshot verdicts compared with the fixed answer key")
table(
    [
        ["Reference verdict", "Graded correct", "Graded incorrect"],
        [
            "Correct",
            str(confusion["correct", "correct"]),
            str(confusion["correct", "incorrect"]),
        ],
        [
            "Incorrect",
            str(confusion["incorrect", "correct"]),
            str(confusion["incorrect", "incorrect"]),
        ],
    ],
    [0.46, 0.27, 0.27],
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

start("Reading-condition replay with recorded distance and illuminance")
paragraph(
    "The Clouclip file reports working distance in centimetres and illuminance in lux at nominal five-second intervals. It contains 77,847 observations from one adult graduate student. We paired three continuous windows from that public recording with independent ASSISTments histories for demonstration. The two datasets describe different people. The source provides sensor readings without an activity label for reading (LumiRead Project, 2026b; Zauner et al., 2026)."
)
section("Table 3. Reminder events on 21 November 2020, original device time")
table(
    [
        ["Window", "Samples", "Reminder opens", "Reminder clears"],
        ["A · Stable", "14", "None", "None"],
        ["B · Distance", "11", "09:10:13", "09:10:28"],
        ["C · Illuminance", "10", "09:45:07", "09:45:37"],
    ],
    [0.36, 0.14, 0.25, 0.25],
)
paragraph(
    "Three consecutive distance readings below 33 cm or light readings below 300 lx trigger the corresponding reminder. The first and third samples span ten seconds. Two consecutive readings at or above 35 cm or 350 lx clear the reminder. B begins with an isolated 25 cm reading, which correctly generates no event. C includes an isolated low distance during the lighting sequence. These cutoffs specify the classroom demonstration (LumiRead Project, 2026b; Zauner et al., 2026)."
)
paragraph(
    "Each window retains its original times and row order. Pause and playback speed change when a point reaches the screen. Sleep, invalid readings and gaps interrupt the relevant consecutive-point count. An active reminder awaits valid recovery evidence. The source file, pinned revision, checksums and original line ranges allow independent reconstruction (LumiRead Project, 2026b; Zauner et al., 2026)."
)
paragraph(
    "An earlier experiment estimated light classes from smartphone images. On 1,563 fixed-exposure observations from a different device, five folds held out whole desk-scene families. Accuracy was 87.91% and macro F1 was 0.8584. The desktop replay instead reads illuminance directly from the public Clouclip sensor file. Neither experiment measures a change in eyesight (Buryi, 2026; LumiRead Project, 2026b; Zauner et al., 2026)."
)

start("Knowledge tracing and the comparison on held-out learners")
paragraph(
    "We retained 44,212 first-attempt answers across 2,362 learners from the corrected, non-collapsed ASSISTments Skill Builder file. The pipeline maps explicit source tags to six skills, merges duplicate tags for one answer and excludes automatically scored open responses. Whole learners belong to training (1,653), validation (354) or test (355). Chronological source order keeps later answers out of each prediction (ASSISTments, 2009–2010; Feng et al., 2009; LumiRead Project, 2026b)."
)
paragraph(
    "The central DKT uses a 12-dimensional embedding and a 24-unit LSTM. Starting from a shared first-question state, it encodes earlier skill and correctness pairs and predicts a probability for each next skill. Training ran on an RTX 4080 SUPER. LightGBM uses the same targets with earlier counts, accuracy and recency. The family notebook runs the frozen central weights on its CPU (Ke et al., 2017; LumiRead Project, 2026b; Piech et al., 2015)."
)
section("Table 4. Results on 6,694 first attempts from 355 held-out learners")
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
section("Table 5. Validation selected each run’s checkpoint before final testing")
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

start("Classroom demonstration and what a pilot would need to establish")
section("A fifteen-minute desktop presentation")
paragraph(
    "The demonstration opens at /showcase. Rotate both product designs and inspect their components. At /app, compare the three family notebooks and replay the stable, short-distance and dim-light windows. In B, upload both versions of the worksheet and compare the two originals and live verdicts. Open a missed item, reveal a hint, review the answer and save it. Submit a practice response and inspect its count and probability (LumiRead Project, 2026b)."
)
paragraph(
    "The acceptance procedure then checks that B retains its work after refresh, A and C retain their own histories, and resetting B restores its starting sequence. At /federated, select seed 16083 and round 58 and compare the displayed values with the saved record. The product assets, six-skill inference and replay run on the demonstration computer. New grading jobs require a configured online provider. The operator can retry a failed job and inspect the recorded status (LumiRead Project, 2026b)."
)
section("Decisions for an optical-store pilot")
paragraph(
    "The largest uncertainty in the business model is repeated family use. Track how many eligible buyers activate a paid plan, how often they return to a graded error, and how many continue at renewal. Record returns, fitting time, active pages per family and support contacts. Together these quantities would replace assumed take-up, retention and costs with observed contribution per hardware buyer (LumiRead Project, 2026a, 2026b)."
)
paragraph(
    "The next evaluation would use permissioned household pages, multiple handwriting styles and independent grading by people. Track missed items, review frequency, incorrect automatic verdicts and whether correction restores the proper history. Separately, test reminder usefulness on children with suitable consent and study design, and evaluate calibration on later locally collected exercises. The submitted prompt and decision log documents how the team revised the capture method and classroom workflow (LumiRead Project, 2026a, 2026b; Zauner et al., 2026)."
)


def reference(title, url=""):
    content = title + (f' <a color="#355b48" href="{url}">{url}</a>' if url else "")
    paragraph(content, hanging=True, space=10)


start("References")
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
reference(
    "Zauner, J., Nicholls, A., Ostrin, L. A., &amp; Spitschan, M. (2026). Analysis of human visual experience data. <i>Journal of Vision, 26</i>(7), Article 1.",
    "https://doi.org/10.1167/jov.26.7.1",
)
c.save()
print(OUT)
