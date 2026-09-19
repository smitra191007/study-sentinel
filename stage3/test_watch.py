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
    audit_path="stage3_test_trace.jsonl",
)

report = watch.run_period(
    cuts=[1],
)

print("Cuts processed:", report.cuts_processed)
print("Decisions:", [d.decision_id for d in report.decisions])
print("Signals:", len(report.signals))
print("First finding:")
print(report.signals[0])