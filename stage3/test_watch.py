from stage2.crew import ReviewCrew
from stage3.watch import StudyWatch


class AtlasHandle:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir


crew = ReviewCrew(
    hub_url="http://localhost:8000",
    gateway_url="http://localhost:8000",
    team_key="test-key",
    atlas=AtlasHandle("hackathon-data"),
    mock_api=True,
)

watch = StudyWatch(
    data_dir="hackathon-data",
    crew=crew,
    audit_path="stage3_full_trace.jsonl",
)

report = watch.run_period(
    cuts=range(1, 13),
)

print()
print("========== STAGE 3 FULL TEST ==========")
print("Cuts processed:", report.cuts_processed)
print("Decisions:", len(report.decisions))
print("Signals:", len(report.signals))
print("Adversarial events:", len(report.adversarial_events))
print("Open items:", len(report.open_items))
print("Budget:", report.budget_used, "/", report.budget_total)
print("Narrative enabled:", report.narrative_enabled)

print()
print("========== IMPORTANT ADVERSARIAL EVENTS ==========")

important = {
    "SITE_SCALE_SHIFT",
    "TAMPERED_DOCUMENT_INSTRUCTION",
    "PROTOCOL_AMENDMENT",
    "LAB_UNIT_ANOMALY",
    "UNRELIABLE_LAB_SITE",
}

for event in report.adversarial_events:
    event_type = event.get("event_type", event.get("type"))

    if event_type in important:
        print(
            event.get("cut"),
            "|",
            event_type,
            "|",
            event.get("site"),
            "|",
            event.get("action"),
        )

print()
print("========== END TEST ==========")