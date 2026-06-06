"""
Configuration — BCG X & McKinsey QuantumBlack Data Science / Analytics Recruitment RAG
Covers: Data Scientist, Analytics Consultant, Data Analyst, Quantitative Analyst roles.
Strictly excludes Data Engineering content.
"""

from dataclasses import dataclass
from typing import List


# ──────────────────────────────────────────────────────────────
# DS / ANALYTICS FILTER KEYWORDS
# ──────────────────────────────────────────────────────────────

DS_INCLUDE_KEYWORDS = [
    # Core roles
    "data scientist", "data science", "analytics", "analytics consultant",
    "data analyst", "quantitative analyst", "insights analyst",
    "advanced analytics", "business intelligence", "quant analyst",
    "statistical analyst", "research analyst", "pricing analyst",
    # Company-specific
    "bcg x", "bcg gamma", "bcg analytics", "boston consulting group",
    "quantumblack", "quantum black", "mckinsey analytics", "mckinsey data",
    "mckinsey quantumblack", "bcg data",
    # Technical / ML
    "machine learning", "ml engineer", "statistical modeling", "statistics",
    "python data", "sql interview", "r programming interview",
    "predictive modeling", "deep learning interview", "nlp interview",
    "a/b testing interview", "experiment design", "causal inference",
    # Interview rounds
    "codesignal", "pair programming", "pei", "tei", "take home case",
    "case interview", "behavioral interview", "online assessment",
    "technical interview data", "fit interview consulting",
    "coding interview data", "problem solving test",
]

DE_EXCLUDE_KEYWORDS = [
    "data engineer", "data engineering", "databricks", "spark", "kafka",
    "airflow", "dbt", "etl", "pipeline engineer", "mlops", "platform engineer",
    "data platform", "data infrastructure", "hadoop", "hive", "flink",
    "streaming pipeline", "data warehouse engineer",
]


# ──────────────────────────────────────────────────────────────
# DATA MODEL
# ──────────────────────────────────────────────────────────────

@dataclass
class ScrapingTarget:
    name: str
    url: str
    company: str          # "BCG" | "McKinsey" | "Both"
    round_type: str       # "OA" | "Technical" | "LiveCoding" | "Case" | "PEI" | "TakeHome" | "General"
    source_type: str      # "article" | "forum" | "reddit" | "glassdoor" | "youtube"
    priority: int = 1
    notes: str = ""
    requires_js: bool = False
    requires_auth: bool = False
    scrape_full_thread: bool = False


# ──────────────────────────────────────────────────────────────
# STATIC / FORUM TARGETS
# ──────────────────────────────────────────────────────────────

STATIC_TARGETS: List[ScrapingTarget] = [

    # ── PrepLounge — forum threads (React SPA → requires Playwright) ──
    ScrapingTarget(
        name="PrepLounge McKinsey DS TEI PEI Pair Programming",
        url="https://www.preplounge.com/consulting-forum/mckinsey-data-science-i-teipei-and-pair-programming-24052",
        company="McKinsey", round_type="LiveCoding", source_type="forum",
        requires_js=True, scrape_full_thread=True,
        notes="Full thread: TEI+PEI+pair programming experiences",
    ),
    ScrapingTarget(
        name="PrepLounge BCG Gamma Data Science Forum",
        url="https://www.preplounge.com/consulting-forum/bcg-gamma-data-science",
        company="BCG", round_type="General", source_type="forum",
        requires_js=True, scrape_full_thread=True,
    ),
    ScrapingTarget(
        name="PrepLounge McKinsey QuantumBlack Forum",
        url="https://www.preplounge.com/consulting-forum/quantumblack-mckinsey-analytics",
        company="McKinsey", round_type="General", source_type="forum",
        requires_js=True, scrape_full_thread=True,
    ),
    ScrapingTarget(
        name="PrepLounge BCG X Data Science Technical Forum",
        url="https://www.preplounge.com/consulting-forum/bcg-x-data-science-interview",
        company="BCG", round_type="Technical", source_type="forum",
        requires_js=True, scrape_full_thread=True,
    ),

    # ── PrepLounge — bootcamp articles (static, trafilatura works) ──
    ScrapingTarget(
        name="PrepLounge McKinsey PEI Guide",
        url="https://www.preplounge.com/en/bootcamp.php/interview-basics/competency-based-interviews/mckinsey-pei",
        company="McKinsey", round_type="PEI", source_type="article",
        scrape_full_thread=True,
    ),
    ScrapingTarget(
        name="PrepLounge BCG Behavioral Interview",
        url="https://www.preplounge.com/en/bootcamp.php/interview-basics/competency-based-interviews/bcg-behavioral-interview",
        company="BCG", round_type="PEI", source_type="article",
        scrape_full_thread=True,
    ),
    ScrapingTarget(
        name="PrepLounge Case Interview Basics",
        url="https://www.preplounge.com/en/case-interview-basics",
        company="Both", round_type="Case", source_type="article",
    ),

    # ── igotanoffer.com — structured interview guides ──
    ScrapingTarget(
        name="IgotAnOffer BCG Data Science Interview",
        url="https://igotanoffer.com/blogs/tech/bcg-data-science-interview",
        company="BCG", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="IgotAnOffer McKinsey Case Interview Prep",
        url="https://igotanoffer.com/blogs/mckinsey-case-interview-prep",
        company="McKinsey", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="IgotAnOffer McKinsey PEI Guide",
        url="https://igotanoffer.com/blogs/mckinsey-case-interview-blog/mckinsey-pei",
        company="McKinsey", round_type="PEI", source_type="article",
    ),
    ScrapingTarget(
        name="IgotAnOffer BCG Fit Interview Guide",
        url="https://igotanoffer.com/blogs/mckinsey-case-interview-blog/bcg-fit-interview",
        company="BCG", round_type="PEI", source_type="article",
    ),
    ScrapingTarget(
        name="IgotAnOffer Data Science Interview Questions",
        url="https://igotanoffer.com/blogs/tech/data-science-interview-questions",
        company="Both", round_type="Technical", source_type="article",
    ),
    ScrapingTarget(
        name="IgotAnOffer McKinsey Data Science Interview",
        url="https://igotanoffer.com/blogs/tech/mckinsey-data-science-interview",
        company="McKinsey", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="IgotAnOffer BCG Interview Process",
        url="https://igotanoffer.com/blogs/mckinsey-case-interview-blog/bcg-interview-process",
        company="BCG", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="IgotAnOffer McKinsey Interview Process",
        url="https://igotanoffer.com/blogs/mckinsey-case-interview-blog/mckinsey-interview-process",
        company="McKinsey", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="IgotAnOffer Python Data Science Interview",
        url="https://igotanoffer.com/blogs/tech/python-data-science-interview-questions",
        company="Both", round_type="Technical", source_type="article",
    ),
    ScrapingTarget(
        name="IgotAnOffer SQL Interview Questions",
        url="https://igotanoffer.com/blogs/tech/sql-interview-questions",
        company="Both", round_type="Technical", source_type="article",
    ),
    ScrapingTarget(
        name="IgotAnOffer Statistics Interview Questions",
        url="https://igotanoffer.com/blogs/tech/statistics-interview-questions",
        company="Both", round_type="Technical", source_type="article",
    ),

    # ── managementconsulted.com — case & behavioral guides ──
    ScrapingTarget(
        name="Management Consulted BCG Interview Guide",
        url="https://managementconsulted.com/bcg-interview/",
        company="BCG", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="Management Consulted McKinsey Interview Guide",
        url="https://managementconsulted.com/mckinsey-interview/",
        company="McKinsey", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="Management Consulted BCG Case Interview",
        url="https://managementconsulted.com/case-interview/bcg-case-interview/",
        company="BCG", round_type="Case", source_type="article",
    ),
    ScrapingTarget(
        name="Management Consulted McKinsey PEI",
        url="https://managementconsulted.com/mckinsey-interview/mckinsey-pei/",
        company="McKinsey", round_type="PEI", source_type="article",
    ),
    ScrapingTarget(
        name="Management Consulted McKinsey Case Interview",
        url="https://managementconsulted.com/case-interview/mckinsey-case-interview/",
        company="McKinsey", round_type="Case", source_type="article",
    ),
    ScrapingTarget(
        name="Management Consulted Data Scientist Interview",
        url="https://managementconsulted.com/data-scientist-interview/",
        company="Both", round_type="Technical", source_type="article",
    ),

    # ── myconsultingcoach.com ──
    ScrapingTarget(
        name="My Consulting Coach BCG Interview",
        url="https://www.myconsultingcoach.com/case-interview/bcg",
        company="BCG", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="My Consulting Coach McKinsey Interview",
        url="https://www.myconsultingcoach.com/case-interview/mckinsey",
        company="McKinsey", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="My Consulting Coach PEI Guide",
        url="https://www.myconsultingcoach.com/case-interview/pei-personal-experience-interview",
        company="Both", round_type="PEI", source_type="article",
    ),

    # ── casecoach.com ──
    ScrapingTarget(
        name="CaseCoach BCG Interview Preparation",
        url="https://casecoach.com/insights/bcg-interview/",
        company="BCG", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="CaseCoach McKinsey Interview",
        url="https://casecoach.com/insights/mckinsey-interview/",
        company="McKinsey", round_type="General", source_type="article",
    ),

    # ── datalemur.com — DS interview Q&A ──
    ScrapingTarget(
        name="DataLemur McKinsey DS Interview Questions",
        url="https://datalemur.com/blog/mckinsey-data-scientist-interview-questions",
        company="McKinsey", round_type="Technical", source_type="article",
    ),
    ScrapingTarget(
        name="DataLemur BCG DS Interview Questions",
        url="https://datalemur.com/blog/bcg-data-scientist-interview-questions",
        company="BCG", round_type="Technical", source_type="article",
    ),
    ScrapingTarget(
        name="DataLemur Data Science Interview Questions",
        url="https://datalemur.com/blog/data-science-interview-questions",
        company="Both", round_type="Technical", source_type="article",
    ),
    ScrapingTarget(
        name="DataLemur Machine Learning Interview Questions",
        url="https://datalemur.com/blog/machine-learning-interview-questions",
        company="Both", round_type="Technical", source_type="article",
    ),
    ScrapingTarget(
        name="DataLemur Statistics Interview Questions",
        url="https://datalemur.com/blog/statistics-interview-questions",
        company="Both", round_type="Technical", source_type="article",
    ),

    # ── stratascratch.com — DS interview prep blog ──
    ScrapingTarget(
        name="StrataScratch DS Interview Questions Guide",
        url="https://www.stratascratch.com/blog/data-science-interview-questions-and-answers/",
        company="Both", round_type="Technical", source_type="article",
    ),
    ScrapingTarget(
        name="StrataScratch DS Interview Process",
        url="https://www.stratascratch.com/blog/how-to-prepare-for-data-science-interviews/",
        company="Both", round_type="General", source_type="article",
    ),

    # ── Original targets ──
    ScrapingTarget(
        name="LinkJob BCG X CodeSignal 2025",
        url="https://www.linkjob.ai/interview-questions/how-i-aced-bcg-x-codesignal-assessment-in-2025/",
        company="BCG", round_type="OA", source_type="article", priority=1,
        notes="CodeSignal types, tips, 2025",
    ),
    ScrapingTarget(
        name="Jigfopsda McKinsey Interview Full Experience",
        url="https://writings.jigfopsda.com/en/posts/2019/mckinsey_interview/",
        company="McKinsey", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="DataInterview BCG Data Scientist",
        url="https://www.datainterview.com/blog/boston-consulting-group-bcg-data-scientist-interview",
        company="BCG", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="DataInterview McKinsey Data Scientist",
        url="https://www.datainterview.com/blog/mckinsey-company-data-scientist-interview",
        company="McKinsey", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="HackingTheCaseInterview BCG X DS",
        url="https://www.hackingthecaseinterview.com/pages/bcg-x-data-scientist-interview",
        company="BCG", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="HackingTheCaseInterview McKinsey DS",
        url="https://www.hackingthecaseinterview.com/pages/mckinsey-data-scientist-interview",
        company="McKinsey", round_type="General", source_type="article",
    ),
    ScrapingTarget(
        name="Grapevine QuantumBlack Senior DS Interview",
        url="https://www.grapevine.in/post/interview-experience-senior-data-scientist-1-quantumblack-mckinsey-98b33689-9b21-4c16-a0e0-e2b45b2c614c",
        company="McKinsey", round_type="General", source_type="article", requires_js=True,
    ),
    ScrapingTarget(
        name="InterviewQuery BCG Data Science",
        url="https://www.interviewquery.com/companies/boston-consulting-group",
        company="BCG", round_type="General", source_type="article",
        requires_js=True,
    ),
    ScrapingTarget(
        name="InterviewQuery McKinsey Data Science",
        url="https://www.interviewquery.com/companies/mckinsey",
        company="McKinsey", round_type="General", source_type="article",
        requires_js=True,
    ),
    ScrapingTarget(
        name="InterviewQuery BCG Interview Experiences",
        url="https://www.interviewquery.com/interview-experiences?companyName=bcg",
        company="BCG", round_type="General", source_type="forum",
        requires_js=True, scrape_full_thread=True,
    ),
    ScrapingTarget(
        name="InterviewQuery McKinsey Interview Experiences",
        url="https://www.interviewquery.com/interview-experiences?companyName=mckinsey",
        company="McKinsey", round_type="General", source_type="forum",
        requires_js=True, scrape_full_thread=True,
    ),

    # ── levels.fyi — interview process descriptions ──
    ScrapingTarget(
        name="Levels.fyi BCG Interview Process",
        url="https://www.levels.fyi/companies/bcg/interviews",
        company="BCG", round_type="General", source_type="article",
        requires_js=True,
    ),
    ScrapingTarget(
        name="Levels.fyi McKinsey Interview Process",
        url="https://www.levels.fyi/companies/mckinsey/interviews",
        company="McKinsey", round_type="General", source_type="article",
        requires_js=True,
    ),

    # ── Quora — Q&A discussions (JS required, login-walled after a few answers) ──
    ScrapingTarget(
        name="Quora BCG X Data Scientist Interview",
        url="https://www.quora.com/search?q=BCG+X+data+scientist+interview",
        company="BCG", round_type="General", source_type="forum",
        requires_js=True, scrape_full_thread=True,
        notes="Search page — extract visible answer snippets",
    ),
    ScrapingTarget(
        name="Quora McKinsey QuantumBlack DS Interview",
        url="https://www.quora.com/search?q=McKinsey+QuantumBlack+data+scientist+interview",
        company="McKinsey", round_type="General", source_type="forum",
        requires_js=True, scrape_full_thread=True,
    ),
    ScrapingTarget(
        name="Quora BCG Data Science Interview Process",
        url="https://www.quora.com/What-is-the-interview-process-for-data-scientists-at-BCG",
        company="BCG", round_type="General", source_type="forum",
        requires_js=True, scrape_full_thread=True,
    ),
    ScrapingTarget(
        name="Quora McKinsey Analytics Interview",
        url="https://www.quora.com/What-is-the-interview-process-like-at-McKinsey-Analytics",
        company="McKinsey", round_type="General", source_type="forum",
        requires_js=True, scrape_full_thread=True,
    ),
]


# ──────────────────────────────────────────────────────────────
# TEAMBLIND SEARCHES
# Dedicated scraper: teamblind_scraper.py
# ──────────────────────────────────────────────────────────────

TEAMBLIND_SEARCHES = [
    # BCG X / BCG Gamma
    {"query": "BCG X data scientist interview",         "company": "BCG",      "round_type": "General",    "max_posts": 15},
    {"query": "BCG gamma analytics interview",          "company": "BCG",      "round_type": "General",    "max_posts": 15},
    {"query": "BCG CodeSignal online assessment",       "company": "BCG",      "round_type": "OA",         "max_posts": 10},
    {"query": "BCG X take home case analytics",         "company": "BCG",      "round_type": "TakeHome",   "max_posts": 10},
    {"query": "BCG pair programming interview",         "company": "BCG",      "round_type": "LiveCoding", "max_posts": 10},
    {"query": "BCG behavioral fit interview PEI",       "company": "BCG",      "round_type": "PEI",        "max_posts": 10},
    # McKinsey QuantumBlack
    {"query": "McKinsey QuantumBlack data scientist",   "company": "McKinsey", "round_type": "General",    "max_posts": 15},
    {"query": "McKinsey pair programming interview",    "company": "McKinsey", "round_type": "LiveCoding", "max_posts": 10},
    {"query": "McKinsey TEI technical interview",       "company": "McKinsey", "round_type": "Technical",  "max_posts": 10},
    {"query": "McKinsey analytics interview data",      "company": "McKinsey", "round_type": "General",    "max_posts": 10},
    {"query": "McKinsey PEI personal experience",       "company": "McKinsey", "round_type": "PEI",        "max_posts": 10},
    {"query": "McKinsey take home case data analysis",  "company": "McKinsey", "round_type": "TakeHome",   "max_posts": 10},
    # Cross-company
    {"query": "consulting data scientist interview",    "company": "Both",     "round_type": "General",    "max_posts": 15},
    {"query": "BCG McKinsey data science vs",           "company": "Both",     "round_type": "General",    "max_posts": 10},
    {"query": "consulting analytics data analyst",      "company": "Both",     "round_type": "General",    "max_posts": 10},
]


# ──────────────────────────────────────────────────────────────
# REDDIT — PRAW CONFIG
# Create a Reddit app at https://www.reddit.com/prefs/apps
# Type: script | Permissions: read
# ──────────────────────────────────────────────────────────────

REDDIT_APP_CONFIG = {
    "client_id":     "YOUR_CLIENT_ID",       # ← replace
    "client_secret": "YOUR_CLIENT_SECRET",   # ← replace
    "user_agent":    "advanced-rag-scraper/2.0 by u/YOUR_USERNAME",
    "username":      "YOUR_USERNAME",        # optional
    "password":      "YOUR_PASSWORD",        # optional
}

# (subreddit, query, company, round_type, min_score, sort)
REDDIT_SEARCHES = [
    # BCG X / BCG Gamma — Data Science & Analytics
    ("datascience",         "BCG X data scientist interview",                 "BCG",      "General",    5,  "top"),
    ("datascience",         "BCG gamma analytics interview",                  "BCG",      "General",    3,  "top"),
    ("datascience",         "BCG take home case data analytics",              "BCG",      "TakeHome",   3,  "top"),
    ("datascience",         "BCG X CodeSignal assessment",                    "BCG",      "OA",         3,  "top"),
    ("datascience",         "BCG X pair programming technical interview",     "BCG",      "LiveCoding", 2,  "top"),
    ("consulting",          "BCG data science interview process",             "BCG",      "General",    5,  "top"),
    ("consulting",          "BCG X analytics recruitment experience",         "BCG",      "General",    3,  "top"),
    ("consulting",          "BCG X data analyst analytics role",              "BCG",      "General",    2,  "top"),
    ("cscareerquestions",   "BCG CodeSignal online assessment tips",          "BCG",      "OA",         5,  "top"),
    ("MachineLearning",     "BCG gamma interview experience machine learning","BCG",      "General",    3,  "top"),
    ("learnmachinelearning","BCG X interview data scientist",                 "BCG",      "General",    2,  "top"),

    # McKinsey QuantumBlack — Data Science & Analytics
    ("datascience",         "McKinsey QuantumBlack data scientist",           "McKinsey", "General",    5,  "top"),
    ("datascience",         "McKinsey pair programming interview Python",     "McKinsey", "LiveCoding", 3,  "top"),
    ("datascience",         "McKinsey take home case data analysis",          "McKinsey", "TakeHome",   3,  "top"),
    ("datascience",         "McKinsey online assessment analytics",           "McKinsey", "OA",         3,  "top"),
    ("datascience",         "McKinsey TEI technical expertise interview",     "McKinsey", "Technical",  2,  "top"),
    ("consulting",          "McKinsey data science analytics interview",      "McKinsey", "General",    5,  "top"),
    ("consulting",          "McKinsey PEI personal experience interview",     "McKinsey", "PEI",        5,  "top"),
    ("consulting",          "McKinsey quantitative case data",                "McKinsey", "Case",       3,  "top"),
    ("consulting",          "McKinsey analytics data scientist experience",   "McKinsey", "General",    3,  "top"),
    ("cscareerquestions",   "McKinsey analytics data science interview",      "McKinsey", "General",    3,  "top"),
    ("MachineLearning",     "McKinsey QuantumBlack interview process ML",    "McKinsey", "General",    2,  "top"),

    # Analytics / Data Analyst consulting roles
    ("datascience",         "data analyst consulting BCG McKinsey interview", "Both",     "General",    3,  "top"),
    ("analytics",           "BCG McKinsey analytics interview experience",    "Both",     "General",    2,  "top"),
    ("analytics",           "consulting analytics data scientist interview",  "Both",     "General",    2,  "top"),
    ("consulting",          "analytics consultant interview case study",      "Both",     "General",    3,  "top"),

    # Cross-company
    ("datascience",         "consulting data scientist interview rounds",     "Both",     "General",    5,  "top"),
    ("consulting",          "data science case interview BCG McKinsey",       "Both",     "Case",       5,  "top"),
    ("datascience",         "BCG gamma take home case analytics python",      "BCG",      "TakeHome",   2,  "top"),
]

# Specific high-value Reddit threads to scrape in full (populate manually)
REDDIT_FULL_THREADS = [
    # Add specific post URLs here after manual discovery
    # e.g. "https://www.reddit.com/r/datascience/comments/abc123/bcg_x_interview_experience/"
]


# ──────────────────────────────────────────────────────────────
# GLASSDOOR — Interview Q&A pages
# Setup (once): python save_glassdoor_session.py  → login via Indeed → session saved
# Then run:     python run_all.py --glassdoor
# ──────────────────────────────────────────────────────────────

GLASSDOOR_TARGETS = [
    # ── Boston Consulting Group (EI_IE3879) — le plus de contenu ─
    {
        "name": "Glassdoor BCG — Data Scientist",
        "url": "https://www.glassdoor.com/Interview/Boston-Consulting-Group-Data-Scientist-Interview-Questions-EI_IE3879.0,23_KO24,38.htm",
        "company": "BCG",
        "round_type": "General",
        "pages": 8,
    },
    {
        "name": "Glassdoor BCG Gamma — Data Scientist",
        "url": "https://www.glassdoor.com/Interview/Boston-Consulting-Group-GAMMA-Data-Scientist-Interview-Questions-EI_IE3879.0,23_KO24,44.htm",
        "company": "BCG",
        "round_type": "General",
        "pages": 6,
    },
    {
        "name": "Glassdoor BCG — Associate Data Scientist",
        "url": "https://www.glassdoor.com/Interview/Boston-Consulting-Group-Associate-Data-Scientist-Interview-Questions-EI_IE3879.0,23_KO24,48.htm",
        "company": "BCG",
        "round_type": "General",
        "pages": 5,
    },
    {
        "name": "Glassdoor BCG — Data Analyst",
        "url": "https://www.glassdoor.com/Interview/Boston-Consulting-Group-Data-Analyst-Interview-Questions-EI_IE3879.0,23_KO24,36.htm",
        "company": "BCG",
        "round_type": "General",
        "pages": 5,
    },
    {
        "name": "Glassdoor BCG — Big Data Analyst",
        "url": "https://www.glassdoor.com/Interview/Boston-Consulting-Group-Big-Data-Analyst-Interview-Questions-EI_IE3879.0,23_KO24,40.htm",
        "company": "BCG",
        "round_type": "General",
        "pages": 4,
    },
    # ── McKinsey & Company (EI_IE2893) ───────────────────────
    {
        "name": "Glassdoor McKinsey — Data Scientist",
        "url": "https://www.glassdoor.com/Interview/McKinsey-and-Company-Data-Scientist-Interview-Questions-EI_IE2893.0,20_KO21,35.htm",
        "company": "McKinsey",
        "round_type": "General",
        "pages": 8,
    },
    {
        "name": "Glassdoor McKinsey — Analytics Consultant",
        "url": "https://www.glassdoor.com/Interview/McKinsey-Company-Analytics-Interview-Questions-EI_IE2893.0,16_KO17,36.htm",
        "company": "McKinsey",
        "round_type": "General",
        "pages": 6,
    },
    {
        "name": "Glassdoor McKinsey — Data Analyst",
        "url": "https://www.glassdoor.com/Interview/McKinsey-and-Company-Data-Analyst-Interview-Questions-EI_IE2893.0,20_KO21,33.htm",
        "company": "McKinsey",
        "round_type": "General",
        "pages": 5,
    },
    {
        "name": "Glassdoor McKinsey — Business Analyst",
        "url": "https://www.glassdoor.com/Interview/McKinsey-and-Company-Business-Analyst-Interview-Questions-EI_IE2893.0,20_KO21,37.htm",
        "company": "McKinsey",
        "round_type": "General",
        "pages": 5,
    },
    # ── QuantumBlack (EI_IE1508182) — 97 questions, 95 reviews ──
    {
        "name": "Glassdoor QuantumBlack — Data Scientist",
        "url": "https://www.glassdoor.com/Interview/QuantumBlack-Data-Scientist-Interview-Questions-EI_IE1508182.0,12_KO13,27.htm",
        "company": "McKinsey",
        "round_type": "General",
        "pages": 8,
    },
    {
        "name": "Glassdoor QuantumBlack — All Interviews",
        "url": "https://www.glassdoor.com/Interview/QuantumBlack-Interview-Questions-EI_IE1508182.0,12.htm",
        "company": "McKinsey",
        "round_type": "General",
        "pages": 10,
    },
]


# ──────────────────────────────────────────────────────────────
# YOUTUBE — DS / Analytics interview queries
# Videos downloaded as MP4, transcribed locally with Whisper
# ──────────────────────────────────────────────────────────────

YOUTUBE_SEARCHES = [
    # BCG X — all rounds
    {"query": "BCG X data scientist interview experience 2024",           "company": "BCG",      "round_type": "General",    "max": 5},
    {"query": "BCG gamma analytics data scientist interview",             "company": "BCG",      "round_type": "General",    "max": 4},
    {"query": "BCG X CodeSignal assessment data science walkthrough",     "company": "BCG",      "round_type": "OA",         "max": 4},
    {"query": "BCG take home case study data analyst presentation",       "company": "BCG",      "round_type": "TakeHome",   "max": 3},
    {"query": "BCG case interview data analytics mock example",           "company": "BCG",      "round_type": "Case",       "max": 4},
    {"query": "BCG fit interview behavioral questions data scientist",    "company": "BCG",      "round_type": "PEI",        "max": 3},
    {"query": "BCG X pair programming Python coding interview",           "company": "BCG",      "round_type": "LiveCoding", "max": 3},
    {"query": "BCG analytics data analyst interview 2024",                "company": "BCG",      "round_type": "General",    "max": 4},

    # McKinsey QuantumBlack — all rounds
    {"query": "McKinsey QuantumBlack data scientist interview process",   "company": "McKinsey", "round_type": "General",    "max": 5},
    {"query": "McKinsey pair programming TEI data science Python",        "company": "McKinsey", "round_type": "LiveCoding", "max": 4},
    {"query": "McKinsey analytics data scientist take home case",         "company": "McKinsey", "round_type": "TakeHome",   "max": 3},
    {"query": "McKinsey case interview quantitative data example",        "company": "McKinsey", "round_type": "Case",       "max": 4},
    {"query": "McKinsey PEI personal experience interview tips stories",  "company": "McKinsey", "round_type": "PEI",        "max": 4},
    {"query": "McKinsey Solve online assessment game walkthrough",        "company": "McKinsey", "round_type": "OA",         "max": 3},
    {"query": "McKinsey analytics interview process data analyst 2024",   "company": "McKinsey", "round_type": "General",    "max": 4},
    {"query": "McKinsey problem solving interview data case",             "company": "McKinsey", "round_type": "Case",       "max": 3},

    # Cross-company & technical
    {"query": "consulting data scientist interview machine learning",      "company": "Both",     "round_type": "Technical",  "max": 4},
    {"query": "data science case interview consulting analytics",          "company": "Both",     "round_type": "Case",       "max": 4},
    {"query": "consulting analytics data scientist Python pandas SQL",     "company": "Both",     "round_type": "Technical",  "max": 4},
    {"query": "data science statistics interview questions probability",   "company": "Both",     "round_type": "Technical",  "max": 3},
    {"query": "machine learning interview questions consulting firm",      "company": "Both",     "round_type": "Technical",  "max": 3},
]

# Max video duration to download
YOUTUBE_MAX_DURATION_SECONDS = 45 * 60  # 45 min

# Whisper model for transcription
WHISPER_MODEL = "base"  # tiny | base | small | medium | large
