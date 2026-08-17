"""Sample assessment questionnaire (blueprint S20).

The questionnaire captures organisational context that metadata cannot see. It
supplements machine evidence and never replaces it: answers are cross-validated
by check GV-009, and a contradiction between a claim and the measurement is
itself a scored finding.
"""

from __future__ import annotations

from typing import Any

QUESTIONNAIRE: list[dict[str, Any]] = [
    {
        "section": "Governance & Metadata",
        "questions": [
            {
                "id": "Q-GOV-01",
                "question": (
                    "Do you operate an enterprise data catalog? Which tool, and what % of Tier-1 "
                    "assets are curated in it?"
                ),
                "answer_type": "percentage_with_note",
                "cross_validates": "GV-004",
            },
            {
                "id": "Q-GOV-02",
                "question": (
                    "What percentage of critical datasets have a named, accountable owner, "
                    "verified within the last 12 months?"
                ),
                "answer_type": "percentage",
                "cross_validates": "GV-001",
            },
            {
                "id": "Q-GOV-03",
                "question": (
                    "What percentage of data assets are classified for sensitivity, and is "
                    "classification enforced mechanically by policy (masking/ACL)?"
                ),
                "answer_type": "percentage_with_note",
                "cross_validates": "SE-001",
            },
            {
                "id": "Q-GOV-04",
                "question": (
                    "What is your column-level lineage coverage for Tier-1 datasets, and is it "
                    "machine-queryable?"
                ),
                "answer_type": "percentage",
                "cross_validates": "MD-005",
            },
        ],
    },
    {
        "section": "Quality & Semantics",
        "questions": [
            {
                "id": "Q-QS-01",
                "question": "Are DQ rules stored as data (rule tables/contracts) or embedded in pipeline code?",
                "answer_type": "choice",
                "options": ["as data", "mixed", "in pipeline code"],
                "cross_validates": "DQ-002",
            },
            {
                "id": "Q-QS-02",
                "question": "What is your mean time to detect and resolve a Tier-1 data incident?",
                "answer_type": "hours",
                "cross_validates": "DQ-004",
            },
            {
                "id": "Q-QS-03",
                "question": (
                    "Are semantic models defined for your certified KPIs, and how many definitions "
                    "exist per KPI (target: exactly one)?"
                ),
                "answer_type": "number_with_note",
                "cross_validates": "SL-001",
            },
            {
                "id": "Q-QS-04",
                "question": (
                    "Can business users query data using natural language today? What is the "
                    "answer-acceptance rate?"
                ),
                "answer_type": "percentage",
                "cross_validates": "SL-005",
            },
        ],
    },
    {
        "section": "AI, Agents & RAG",
        "questions": [
            {
                "id": "Q-AI-01",
                "question": (
                    "Do you support vector search in production? What is the embedding refresh SLA "
                    "relative to the content change rate?"
                ),
                "answer_type": "text",
                "cross_validates": "RG-004",
            },
            {
                "id": "Q-AI-02",
                "question": (
                    "Do AI agents operate under identities distinct from humans, with per-agent "
                    "scoped entitlements?"
                ),
                "answer_type": "yes_no_with_note",
                "cross_validates": "AG-004",
            },
            {
                "id": "Q-AI-03",
                "question": (
                    "Can you reconstruct, from logs, every data element an agent accessed to "
                    "produce a given output?"
                ),
                "answer_type": "yes_no_with_note",
                "cross_validates": "AG-006",
            },
            {
                "id": "Q-AI-04",
                "question": (
                    "Is there a human approval gate before AI-generated artefacts (models, "
                    "pipelines, rules) are promoted to production?"
                ),
                "answer_type": "yes_no_with_note",
                "cross_validates": "AE-005",
            },
            {
                "id": "Q-AI-05",
                "question": (
                    "For RAG: do document ACLs propagate to your vector indexes, and is filtering "
                    "enforced at retrieval time?"
                ),
                "answer_type": "yes_no_with_note",
                "cross_validates": "RG-005",
            },
        ],
    },
]


def question_index() -> dict[str, dict[str, Any]]:
    return {q["id"]: q for section in QUESTIONNAIRE for q in section["questions"]}
