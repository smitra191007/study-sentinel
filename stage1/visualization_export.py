import csv
import json
import os
import sys


def write_csv(path, rows, fieldnames):
    with open(
        path,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def load_review_queue(data_dir):
    """
    Load the actual ATLAS human review queue.

    One review entry represents one actual finding.
    """

    review_path = os.path.join(
        data_dir,
        "review_queue.json",
    )

    if not os.path.exists(review_path):
        return []

    with open(
        review_path,
        encoding="utf-8",
    ) as f:
        return json.load(f)


def build_review_lookup(review_queue):
    """
    Create a lookup from finding information to review information.

    Multiple findings can have identical subject/finding/category
    combinations, so we keep a list for each key.
    """

    lookup = {}

    for item in review_queue:

        key = (
            item.get("category", ""),
            item.get("finding", ""),
            item.get("subject_id", ""),
        )

        lookup.setdefault(
            key,
            [],
        ).append(item)

    return lookup


def main():

    data_dir = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "."
    )

    # -----------------------------------------------------
    # INPUT FILES
    # -----------------------------------------------------

    stage1_path = os.path.join(
        data_dir,
        "stage1_public.json",
    )

    graph_path = os.path.join(
        data_dir,
        "graph_stats.json",
    )

    # -----------------------------------------------------
    # LOAD ATLAS OUTPUT
    # -----------------------------------------------------

    with open(
        stage1_path,
        encoding="utf-8",
    ) as f:
        findings = json.load(f)

    # -----------------------------------------------------
    # LOAD GRAPH STATS
    # -----------------------------------------------------

    with open(
        graph_path,
        encoding="utf-8",
    ) as f:
        graph = json.load(f)

    # -----------------------------------------------------
    # LOAD REVIEW QUEUE
    # -----------------------------------------------------

    review_queue = load_review_queue(
        data_dir
    )

    review_lookup = build_review_lookup(
        review_queue
    )

    # -----------------------------------------------------
    # OUTPUT DIRECTORY
    # -----------------------------------------------------

    output_dir = os.path.join(
        data_dir,
        "powerbi",
    )

    os.makedirs(
        output_dir,
        exist_ok=True,
    )

    # =====================================================
    # 1. STUDY SUMMARY
    # =====================================================

    summary_rows = [
        {
            "metric": "Subjects",
            "value": graph["n_subjects"],
        },
        {
            "metric": "Sites",
            "value": graph["n_sites"],
        },
        {
            "metric": "Domains",
            "value": len(
                graph["records_per_domain"]
            ),
        },
    ]

    write_csv(
        os.path.join(
            output_dir,
            "study_summary.csv",
        ),
        summary_rows,
        [
            "metric",
            "value",
        ],
    )

    # =====================================================
    # 2. RECORDS BY DOMAIN
    # =====================================================

    domain_rows = [
        {
            "domain": domain,
            "record_count": count,
        }
        for domain, count
        in graph["records_per_domain"].items()
    ]

    write_csv(
        os.path.join(
            output_dir,
            "domain_records.csv",
        ),
        domain_rows,
        [
            "domain",
            "record_count",
        ],
    )

    # =====================================================
    # 3. SUBJECTS BY SITE
    # =====================================================

    site_rows = [
        {
            "site": site,
            "subject_count": count,
        }
        for site, count
        in graph["subjects_per_site"].items()
    ]

    write_csv(
        os.path.join(
            output_dir,
            "site_subjects.csv",
        ),
        site_rows,
        [
            "site",
            "subject_count",
        ],
    )

    # =====================================================
    # 4. FLATTEN ATLAS FINDINGS
    # =====================================================

    finding_rows = []

    finding_categories = [
        "hys_law_candidates",
        "seriousness_miscoded",
        "prohibited_medication_use",
        "dosing_errors",
        "visit_window_deviations",
        "embedded_instructions_detected_not_followed",
    ]

    for category in finding_categories:

        for item in findings.get(
            category,
            [],
        ):

            evidence = item.get(
                "evidence",
                [],
            )

            subject_id = item.get(
                "usubjid",
                "",
            )

            finding_type = item.get(
                "finding",
                "",
            )

            # -------------------------------------------------
            # FIND REVIEW QUEUE ENTRY
            # -------------------------------------------------

            review_key = (
                category,
                finding_type,
                subject_id,
            )

            matching_reviews = review_lookup.get(
                review_key,
                [],
            )

            # Pop one review entry when multiple identical
            # findings exist.
            if matching_reviews:

                review_item = matching_reviews.pop(0)

                review_id = review_item.get(
                    "review_id",
                    "",
                )

                review_priority = review_item.get(
                    "review_priority",
                    "",
                )

                review_status = review_item.get(
                    "review_status",
                    "PENDING",
                )

            else:

                review_id = ""

                review_priority = ""

                review_status = ""

            # -------------------------------------------------
            # FINDINGS WITH EVIDENCE
            # -------------------------------------------------

            if evidence:

                for ev in evidence:

                    finding_rows.append(
                        {
                            "review_id": review_id,

                            "review_priority": review_priority,

                            "review_status": review_status,

                            "subject_id": subject_id,

                            "finding_category": category,

                            "finding_type": finding_type,

                            "evidence_domain": ev[0],

                            "evidence_subject": ev[1],

                            "evidence_seq": ev[2],

                            "detail": item.get(
                                "detail",
                                "",
                            ),
                        }
                    )

            # -------------------------------------------------
            # FINDINGS WITHOUT EVIDENCE
            # -------------------------------------------------

            else:

                finding_rows.append(
                    {
                        "review_id": review_id,

                        "review_priority": review_priority,

                        "review_status": review_status,

                        "subject_id": subject_id,

                        "finding_category": category,

                        "finding_type": finding_type,

                        "evidence_domain": "",

                        "evidence_subject": "",

                        "evidence_seq": "",

                        "detail": item.get(
                            "line",
                            item.get(
                                "detail",
                                "",
                            ),
                        ),
                    }
                )

    # =====================================================
    # 5. WRITE FINDINGS CSV
    # =====================================================

    write_csv(
        os.path.join(
            output_dir,
            "findings.csv",
        ),
        finding_rows,
        [
            "review_id",
            "review_priority",
            "review_status",
            "subject_id",
            "finding_category",
            "finding_type",
            "evidence_domain",
            "evidence_subject",
            "evidence_seq",
            "detail",
        ],
    )

    # =====================================================
    # 6. PRINT RESULT
    # =====================================================

    print(
        "Power BI export completed."
    )

    print(
        f"Output folder: {output_dir}"
    )

    print(
        f"Findings rows: {len(finding_rows)}"
    )

    print(
        f"Review queue entries: {len(review_queue)}"
    )

    print("Created:")

    print(
        "  study_summary.csv"
    )

    print(
        "  domain_records.csv"
    )

    print(
        "  site_subjects.csv"
    )

    print(
        "  findings.csv"
    )


if __name__ == "__main__":
    main()