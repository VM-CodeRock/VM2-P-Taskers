"""Default Changeis-relevant NAICS/agency/keyword config for the Tango monitor.

These mirror the priority set used by the existing VM2-OPP SAM monitor
(``backups/scripts/run_sam_monitor.py``) plus a few IT/consulting codes used
by the Changeis opportunity DB (``backups/scripts/build_opportunity_db.py``).
Override via --naics / --agency / --keyword-cluster CLI flags.
"""

from __future__ import annotations

from typing import Dict, List

# Matches run_sam_monitor.py NAICS_CODES
PRIORITY_NAICS: List[str] = [
    "541511", "541512", "541513", "541519",
    "541611", "541612", "541613", "541614", "541618",
    "541715", "541990",
]

# Agencies Changeis actively pursues — names as Tango typically stores them.
PRIORITY_AGENCIES: List[str] = [
    "Department of Defense",
    "Department of the Army",
    "Department of the Navy",
    "Department of the Air Force",
    "Department of Homeland Security",
    "Department of Veterans Affairs",
    "Department of Health and Human Services",
    "General Services Administration",
    "Department of Transportation",
    "Federal Aviation Administration",
    "Department of Justice",
    "Department of State",
]

# Keyword clusters for attachment-search. Each cluster is a single full-text
# query sent to /api/opportunities/attachment-search/; hits are tagged with
# the cluster name so scorers downstream can weight them.
KEYWORD_CLUSTERS: Dict[str, str] = {
    "ai_ml": "artificial intelligence OR machine learning OR large language model OR generative AI",
    "data_analytics": "data analytics OR data engineering OR data science OR business intelligence",
    "cloud_modernization": "cloud migration OR application modernization OR DevSecOps OR zero trust",
    "agile_delivery": "agile delivery OR scaled agile OR human-centered design OR product management",
    "program_management": "program management OR PMO OR acquisition support OR portfolio management",
    "cyber": "cybersecurity OR RMF OR FISMA OR continuous monitoring",
}

# Recompete expiry window in days — contracts whose ultimate completion date
# falls inside this forward window are treated as potential recompetes.
RECOMPETE_WINDOW_DAYS: int = 365
