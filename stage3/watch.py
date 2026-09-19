from stage2.crew import ReviewCrew

class AtlasHandle:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir


# ---------------------------------------------------------
# Stage 2 Crew
# ---------------------------------------------------------

crew = ReviewCrew(
    hub_url="http://localhost:8000",
    gateway_url="http://localhost:8000",
    team_key="test-key",
    atlas=AtlasHandle("hackathon-data"),
    mock_api=True,
)


# ---------------------------------------------------------
# Stage 3 WATCH
# ---------------------------------------------------------

watch = StudyWatch(
    data_dir="hackathon-data",
    crew=crew,
    audit_path="stage3_test_trace.jsonl",
)


# ---------------------------------------------------------
# Run ALL 12 cuts
# ---------------------------------------------------------

report = watch.run_period(
    cuts=range(1, 13)
)


# ---------------------------------------------------------
# Results
# ---------------------------------------------------------

print("\n" + "=" * 60)
print("STAGE 3 WATCH — 12 CUT RUN")
print("=" * 60)

print("\nCuts processed:")
print(report.cuts_processed)

print("\nNumber of decisions:")
print(len(report.decisions))

print("\nNumber of signals:")
print(len(report.signals))


# ---------------------------------------------------------
# Print every signal
# ---------------------------------------------------------

print("\n" + "-" * 60)
print("SIGNALS")
print("-" * 60)

for signal in report.signals:
    print(
        f"\nFinding ID : {signal.finding_id}"
        f"\nCode       : {signal.code}"
        f"\nSubject    : {signal.usubjid}"
        f"\nSite       : {signal.site}"
        f"\nStatus     : {signal.status}"
        f"\nProtocol   : v{signal.protocol_version}"
        f"\nRationale  : {signal.rationale}"
        f"\nTrail      : {' -> '.join(signal.node_trail)}"
    )


# ---------------------------------------------------------
# Print decisions
# ---------------------------------------------------------

print("\n" + "-" * 60)
print("DECISIONS")
print("-" * 60)

for decision in report.decisions:
    print(decision.decision_id)


# ---------------------------------------------------------
# First finding
# ---------------------------------------------------------

if report.signals:
    print("\n" + "-" * 60)
    print("FIRST FINDING")
    print("-" * 60)

    print(report.signals[0])


print("\n" + "=" * 60)
print("12-CUT RUN COMPLETE")
print("=" * 60)