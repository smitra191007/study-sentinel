"""
ATLAS Human Review Queue

Uses the actual findings produced by ATLAS.

Review priority is a deterministic workflow ordering.
It is NOT a clinical severity score.

The human reviewer makes the final disposition.
"""

import hashlib
import json
import os


# ---------------------------------------------------------
# REVIEW PRIORITY
# ---------------------------------------------------------
# This is the project's workflow order for human review.
# It is NOT an official clinical severity scale.

REVIEW_PRIORITY = {
    "HYS_LAW_CANDIDATE": 1,
    "SERIOUS_AE_HOSPITALIZATION_OVERRIDE": 2,
    "DOSING_ERROR": 3,
    "PROHIBITED_MEDICATION": 4,
    "VISIT_WINDOW_DEVIATION": 5,
    "EMBEDDED_INSTRUCTION": 6,
}


# ---------------------------------------------------------
# CATEGORY FALLBACK
# ---------------------------------------------------------
# Used if a finding does not contain one of the explicit
# finding types above.

CATEGORY_PRIORITY = {
    "hys_law_candidates": 1,
    "seriousness_miscoded": 2,
    "dosing_errors": 3,
    "prohibited_medication_use": 4,
    "visit_window_deviations": 5,
    "embedded_instructions_detected_not_followed": 6,
}


# ---------------------------------------------------------
# FINDING CATEGORIES INCLUDED IN HUMAN REVIEW
# ---------------------------------------------------------

REVIEWABLE_CATEGORIES = (
    "hys_law_candidates",
    "seriousness_miscoded",
    "dosing_errors",
    "prohibited_medication_use",
    "visit_window_deviations",
    "embedded_instructions_detected_not_followed",
)


# ---------------------------------------------------------
# GET REVIEW PRIORITY
# ---------------------------------------------------------

def get_review_priority(finding_type, category=None):
    """
    Return the deterministic review priority.

    Lower number = earlier human review.

    Example:
        HYS_LAW_CANDIDATE -> 1
        DOSING_ERROR -> 3
    """

    if finding_type in REVIEW_PRIORITY:
        return REVIEW_PRIORITY[finding_type]

    if category in CATEGORY_PRIORITY:
        return CATEGORY_PRIORITY[category]

    # Unknown findings go to the end.
    return 99


# ---------------------------------------------------------
# CREATE STABLE REVIEW ID
# ---------------------------------------------------------

def _make_review_id(category, finding):
    """
    Create a stable identifier for one review entry.

    The ID is generated from the actual ATLAS finding.
    """

    raw = json.dumps(
        {
            "category": category,
            "finding": finding,
        },
        sort_keys=True,
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:16]


# ---------------------------------------------------------
# BUILD HUMAN REVIEW QUEUE
# ---------------------------------------------------------

def build_review_queue(findings):
    """
    Convert actual ATLAS findings into a human review queue.

    One queue entry = one actual ATLAS finding.

    The queue contains:
        - review_id
        - category
        - review_priority
        - finding
        - subject_id
        - evidence
        - detail
        - review_status
        - reviewer
        - review_note
    """

    queue = []

    for category in REVIEWABLE_CATEGORIES:

        category_findings = findings.get(
            category,
            [],
        )

        if not isinstance(
            category_findings,
            list,
        ):
            continue

        for finding in category_findings:

            if not isinstance(
                finding,
                dict,
            ):
                continue

            finding_type = finding.get(
                "finding",
                category,
            )

            priority = get_review_priority(
                finding_type,
                category,
            )

            review_entry = {
                "review_id": _make_review_id(
                    category,
                    finding,
                ),

                "category": category,

                "review_priority": priority,

                "finding": finding_type,

                "subject_id": finding.get(
                    "usubjid",
                    "",
                ),

                "evidence": finding.get(
                    "evidence",
                    [],
                ),

                "detail": finding.get(
                    "detail",
                    "",
                ),

                # Human review starts as pending.
                "review_status": "PENDING",

                # Filled by reviewer later.
                "reviewer": "",

                "review_note": "",
            }

            queue.append(
                review_entry
            )

    # -----------------------------------------------------
    # SORT BY REVIEW PRIORITY
    # -----------------------------------------------------
    #
    # Priority 1 appears first,
    # followed by Priority 2, etc.
    #

    queue.sort(
        key=lambda item: item[
            "review_priority"
        ]
    )

    return queue


# ---------------------------------------------------------
# REVIEW SUMMARY
# ---------------------------------------------------------

def review_summary(queue):
    """
    Create a summary of the human review queue.
    """

    summary = {
        "total_findings": len(queue),
        "pending": 0,
        "by_priority": {},
        "by_category": {},
    }

    for item in queue:

        # Count pending reviews.
        if item.get(
            "review_status"
        ) == "PENDING":

            summary["pending"] += 1

        # Count by priority.
        priority = str(
            item.get(
                "review_priority",
                99,
            )
        )

        summary["by_priority"][priority] = (
            summary["by_priority"].get(
                priority,
                0,
            )
            + 1
        )

        # Count by category.
        category = item.get(
            "category",
            "",
        )

        summary["by_category"][category] = (
            summary["by_category"].get(
                category,
                0,
            )
            + 1
        )

    return summary


# ---------------------------------------------------------
# UPDATE REVIEW STATUS
# ---------------------------------------------------------

def update_review_status(
    queue,
    review_id,
    status,
    reviewer="",
    review_note="",
):
    """
    Update the human review decision for one finding.

    Allowed statuses:
        PENDING
        CONFIRMED
        REJECTED
        NEEDS_QUERY
        ESCALATED
    """

    allowed_statuses = {
        "PENDING",
        "CONFIRMED",
        "REJECTED",
        "NEEDS_QUERY",
        "ESCALATED",
    }

    if status not in allowed_statuses:
        raise ValueError(
            f"Invalid review status: {status}"
        )

    for item in queue:

        if item.get(
            "review_id"
        ) == review_id:

            item["review_status"] = status

            item["reviewer"] = reviewer

            item["review_note"] = review_note

            return True

    return False


# ---------------------------------------------------------
# SAVE REVIEW QUEUE
# ---------------------------------------------------------

def save_review_queue(
    queue,
    path,
):
    """
    Save the human review queue as JSON.

    One entry = one actual ATLAS finding.
    """

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            queue,
            f,
            indent=2,
        )


# ---------------------------------------------------------
# LOAD REVIEW QUEUE
# ---------------------------------------------------------

def load_review_queue(path):
    """
    Load a previously generated review queue.
    """

    with open(
        path,
        encoding="utf-8",
    ) as f:

        return json.load(f)


# ---------------------------------------------------------
# COMMAND-LINE EXPORT
# ---------------------------------------------------------

if __name__ == "__main__":

    # Current project directory.
    data_dir = "."

    # ATLAS output.
    stage1_path = os.path.join(
        data_dir,
        "stage1_public.json",
    )

    # Human review queue output.
    output_path = os.path.join(
        data_dir,
        "review_queue.json",
    )

    # -----------------------------------------------------
    # LOAD ACTUAL ATLAS FINDINGS
    # -----------------------------------------------------

    with open(
        stage1_path,
        encoding="utf-8",
    ) as f:

        findings = json.load(f)

    # -----------------------------------------------------
    # BUILD REVIEW QUEUE
    # -----------------------------------------------------

    queue = build_review_queue(
        findings
    )

    # -----------------------------------------------------
    # SAVE REVIEW QUEUE
    # -----------------------------------------------------

    save_review_queue(
        queue,
        output_path,
    )

    # -----------------------------------------------------
    # CREATE SUMMARY
    # -----------------------------------------------------

    summary = review_summary(
        queue
    )

    # -----------------------------------------------------
    # PRINT RESULT
    # -----------------------------------------------------

    print(
        "ATLAS review queue created."
    )

    print(
        f"Review entries: {len(queue)}"
    )

    print(
        f"Output: {output_path}"
    )

    print(
        json.dumps(
            summary,
            indent=2,
        )
    )