# VM2-OPP Deep Dive Execution Specification

## Overview

When the hourly vm2-opp cron picks up a Todoist task with the `vm2-opp` label, it executes this full deep-dive analysis and produces a branded Changeis Opportunity Deep Dive Brief.

## Input

The Todoist task contains:
- **Title**: Opportunity name (optionally with solicitation number)
- **Description**: Structured metadata block between `---VM2-OPP-METADATA---` markers

Parse the metadata JSON to get: solicitation_number, notice_id, agency, naics, rag_score, sam_url, source, posted_date, response_deadline, best_match, value_range.

## Execution Steps

### Step 1: Opportunity Data Collection
1. If `sam_url` is provided, fetch the full SAM.gov opportunity details (use SAM.gov internal APIs or browser_task if needed)
2. Pull any attachments referenced (SOW, SOO, PWS, RFP document links)
3. Extract: full description, contact info, set-aside type, place of performance, contract type, estimated value

### Step 2: RAG Engine — Unlimited Matching
1. Call the Changeis BD RAG Engine: `POST /match` with `top_n: 50` (not limited to top 5)
2. Query: opportunity title + agency + NAICS + any scope description
3. For ALL matches with score >= 0.45 (not just STRONG):
   - Record contract number, agency, Volpe/FAA/FHWA association, score
   - These become the basis for capability matrices and corporate experience
4. Group matches by:
   - STRONG (>=0.65): Primary pursuit evidence
   - MODERATE (0.50-0.64): Supporting/teaming evidence  
   - RELEVANT (0.45-0.49): Background evidence for breadth claims

### Step 3: FPDS Incumbent Research
1. Search FPDS.gov for the solicitation number or related contract numbers
2. Identify:
   - Current incumbent contractor(s)
   - Contract value and period of performance
   - Option years remaining
   - Any task order history under the same IDIQ
3. If no solicitation number, search by agency + NAICS + keywords

### Step 4: USAspending.gov Analysis
1. Search USAspending for the agency's spending in the relevant NAICS code(s)
2. Extract:
   - Total annual spend in this NAICS
   - Top 5 contractors by award value
   - Trend (increasing/decreasing over 3 years)
   - Average contract size
   - Small business vs. full-and-open split

### Step 5: Agency & Competitive Landscape
1. Research the specific agency/office:
   - Recent acquisition priorities
   - Key decision-makers (if public)
   - Related active/upcoming procurements
2. Identify top competitors likely to bid:
   - Based on FPDS incumbent data
   - Based on USAspending top contractors
   - Known competitors in this NAICS from prior analysis

### Step 6: Capability Matrix Draft
Using all RAG matches (Step 2), generate:

**Capability Matrix Table**
| Requirement Area | Changeis Past Performance | Contract # | Agency | Relevance Score | Key Deliverables |
|---|---|---|---|---|---|
| [Extracted from SOW/opportunity] | [Matched contract summary] | V32xxxxx | FAA/DOT | 0.72 | [Specific deliverables] |

This table directly maps opportunity requirements to Changeis past performance — ready to be dropped into a proposal's capability matrix or corporate experience section.

### Step 7: Corporate Experience Narrative Seeds
For each STRONG match (>=0.65), generate a 2-3 sentence corporate experience narrative seed:
- Contract name and number
- Agency and scope alignment
- Specific deliverables/outcomes that map to this opportunity
- These are drafts that can be refined for the actual proposal

### Step 8: Go/No-Go Assessment
Produce a structured recommendation:
- **Fit Score**: Weighted average of RAG matches, adjusted for incumbent risk
- **Strengths**: Top 3 alignment points with evidence
- **Gaps**: Requirements where Changeis lacks direct evidence
- **Risk Factors**: Incumbent advantage, set-aside limitations, timeline pressure
- **Teaming Recommendation**: If score is MODERATE, suggest specific teaming strategy (prime vs sub, what type of partner needed)
- **Decision**: PURSUE / PURSUE WITH PARTNER / MONITOR / PASS
- **Next Actions**: 3-5 specific steps with owners and deadlines

## Output: Deep Dive Brief HTML

Branded Changeis HTML deliverable with these sections:

1. **Header**: VM2 · DEEP DIVE BRIEF | Date | Opportunity Title
2. **Executive Summary Card**: 
   - Decision recommendation (color-coded)
   - RAG score | Agency | NAICS | Response deadline
   - One-line verdict
3. **Opportunity Overview**: Full details from SAM.gov
4. **Past Performance Matrix**: Full capability matrix table (unlimited matches)
5. **Corporate Experience Seeds**: Narrative drafts for strong matches  
6. **Incumbent & Market Analysis**: FPDS data, USAspending trends
7. **Competitive Landscape**: Known competitors, win probability assessment
8. **Go/No-Go Assessment**: Full structured recommendation
9. **Next Actions**: Prioritized action items with timeline
10. **Sources**: All URLs used

## Auto-Dive Rules

When the daily brief cron generates the combined report:
1. Any opportunity with RAG score >= 0.65 (STRONG) automatically gets a Todoist task created with `vm2-opp` label
2. The auto-created task description includes `"auto_dive": true` in the metadata
3. The daily brief marks these with a badge: "Auto Deep Dive Queued"
4. The hourly cron then processes them like any other deep-dive request

## File Naming & Publishing

- Filename: `deep-dive-{slug}-{YYYY-MM-DD}.html`
- Slug: kebab-case of opportunity title (max 50 chars)
- Push to: `vm-coderock/VM2-P-Taskers` repo (plain HTML, no encryption)
- Update index.html with badge type: `badge-research`
- Save to Dropbox: `V M2/VM2-main-folder/VM2-P/`

## Post-Completion

1. Add a comment to the Todoist task with the deliverable URL
2. Mark the Todoist task complete
3. Apply `vm2-done` label
4. Send notification: "Deep Dive ready: {title} — {decision recommendation}"
