import json
from pathlib import Path
from typing import Any, Dict

from .models import SurveillanceReport


def build_public_report(
    report: SurveillanceReport,
) -> Dict[str, Any]:
    """
    Convert the internal surveillance report into a
    non-technical reviewer-friendly structure.
    """

    return {
        "summary": {
            "cuts_processed": report.cuts_processed,
            "total_signals": len(report.signals),
            "total_site_risk_items": len(report.site_risk),
            "total_deviations": len(report.deviations),
            "total_adversarial_events": len(
                report.adversarial_events
            ),
            "total_open_items": len(
                report.open_items
            ),
        },
        "signals": report.signals,
        "site_risk": report.site_risk,
        "deviations": report.deviations,
        "adversarial_events": report.adversarial_events,
        "open_items": report.open_items,
        "budget": {
            "total": report.budget_total,
            "used": report.budget_used,
            "narrative_enabled": report.narrative_enabled,
        },
        "decisions": [
            decision.to_dict()
            for decision in report.decisions
        ],
    }


def write_public_report(
    report: SurveillanceReport,
    path: str = "surveillance_report.json",
) -> str:
    """
    Write the public surveillance report as JSON.
    """

    output = build_public_report(report)

    destination = Path(path)

    with destination.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    return str(destination)


def write_public_report_markdown(
    report: SurveillanceReport,
    path: str = "surveillance_report.md",
) -> str:
    """
    Write a readable Markdown version for non-technical reviewers.
    """

    lines = []

    lines.append("# Study Surveillance Report")
    lines.append("")

    lines.append("## Summary")
    lines.append("")

    lines.append(
        f"- Cuts processed: {report.cuts_processed}"
    )

    lines.append(
        f"- Signals: {len(report.signals)}"
    )

    lines.append(
        f"- Site-risk items: {len(report.site_risk)}"
    )

    lines.append(
        f"- Deviations: {len(report.deviations)}"
    )

    lines.append(
        f"- Adversarial events: "
        f"{len(report.adversarial_events)}"
    )

    lines.append(
        f"- Open items: {len(report.open_items)}"
    )

    lines.append("")

    lines.append("## Signals")
    lines.append("")

    if report.signals:
        for signal in report.signals:
            lines.append(
                f"- {signal}"
            )
    else:
        lines.append(
            "- No signals recorded."
        )

    lines.append("")

    lines.append("## Site Risk")
    lines.append("")

    if report.site_risk:
        for item in report.site_risk:
            lines.append(
                f"- {item}"
            )
    else:
        lines.append(
            "- No site-risk items recorded."
        )

    lines.append("")

    lines.append("## Deviations")
    lines.append("")

    if report.deviations:
        for item in report.deviations:
            lines.append(
                f"- {item}"
            )
    else:
        lines.append(
            "- No deviations recorded."
        )

    lines.append("")

    lines.append("## Adversarial Events")
    lines.append("")

    if report.adversarial_events:
        for item in report.adversarial_events:
            lines.append(
                f"- {item}"
            )
    else:
        lines.append(
            "- No adversarial events recorded."
        )

    lines.append("")

    lines.append("## Open Items")
    lines.append("")

    if report.open_items:
        for item in report.open_items:
            lines.append(
                f"- {item}"
            )
    else:
        lines.append(
            "- No open items recorded."
        )

    lines.append("")

    lines.append("## Budget")
    lines.append("")

    lines.append(
        f"- Budget total: {report.budget_total}"
    )

    lines.append(
        f"- Budget used: {report.budget_used}"
    )

    lines.append(
        f"- Narrative work enabled: "
        f"{report.narrative_enabled}"
    )

    lines.append("")

    return_text = "\n".join(lines)

    destination = Path(path)

    destination.write_text(
        return_text,
        encoding="utf-8",
    )

    return str(destination)