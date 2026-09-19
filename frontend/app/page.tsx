"use client";

import { useMemo, useState } from "react";

type Page =
  | "Overview"
  | "Review Queue"
  | "Sites"
  | "Subjects"
  | "Queries"
  | "Human Gate"
  | "Surveillance"
  | "Audit Trail";

type Priority = "P0" | "P1" | "P2" | "P3";

type Signal = {
  id: string;
  title: string;
  type: string;
  site: string;
  subject?: string;
  cut: number;
  priority: Priority;
  status: string;
  action: string;
  evidence: string[];
  rationale: string;
};

const nav: { name: Page; icon: string }[] = [
  { name: "Overview", icon: "⌂" },
  { name: "Review Queue", icon: "!" },
  { name: "Sites", icon: "◉" },
  { name: "Subjects", icon: "♙" },
  { name: "Queries", icon: "?" },
  { name: "Human Gate", icon: "✓" },
  { name: "Surveillance", icon: "◷" },
  { name: "Audit Trail", icon: "≡" },
];

const signals: Signal[] = [
  {
    id: "D-014",
    title: "Serious adverse event detected",
    type: "Clinical Safety",
    site: "S12",
    subject: "SUBJ-204",
    cut: 7,
    priority: "P0",
    status: "OPEN",
    action: "Immediate medical escalation",
    evidence: [
      "AE-204-07",
      "Severity = Serious",
      "Hospitalization recorded",
    ],
    rationale:
      "The event meets the configured serious-event criteria and requires same-cut medical review.",
  },
  {
    id: "D-008",
    title: "Laboratory distribution shift",
    type: "Data Integrity",
    site: "S04",
    subject: "SUBJ-041",
    cut: 8,
    priority: "P1",
    status: "UNTRUSTED",
    action: "Exclude from safety + query laboratory",
    evidence: [
      "S04 GLUC median before = 118 mg/dL",
      "Cut 8 GLUC = 6.4 mg/dL",
      "Ratio ≈ 0.054",
      "Possible ×18 unit conversion",
    ],
    rationale:
      "The magnitude and conversion-factor pattern indicate a likely unit problem. No matching clinical evidence supports treating this as a patient emergency.",
  },
  {
    id: "D-011",
    title: "Suspicious site regularity",
    type: "Adversarial Integrity",
    site: "S09",
    cut: 6,
    priority: "P1",
    status: "QUARANTINED",
    action: "Quarantine from safety analysis + audit",
    evidence: [
      "Implausibly regular observations",
      "Repeated identical patterns",
      "Site-level distribution anomaly",
    ],
    rationale:
      "The site's observation pattern is inconsistent with expected variability and requires integrity review.",
  },
  {
    id: "D-013",
    title: "Protocol document modification",
    type: "Document Integrity",
    site: "ALL",
    cut: 9,
    priority: "P1",
    status: "LOGGED",
    action: "Ignore reviewer instruction + record tampering",
    evidence: [
      "protocol_v3 modified",
      "New automated-reviewer instruction detected",
      "Document re-read",
    ],
    rationale:
      "The document was re-read after modification. The embedded instruction was treated as untrusted content rather than an executable directive.",
  },
  {
    id: "D-006",
    title: "Derived finding recomputed",
    type: "Amendment",
    site: "S07",
    cut: 5,
    priority: "P2",
    status: "RECOMPUTED",
    action: "Recalculate affected derived variables",
    evidence: [
      "Amendment received",
      "Derived variable dependency affected",
      "Earlier finding recalculated",
    ],
    rationale:
      "The amendment invalidated a previously derived value, so dependent findings were recomputed.",
  },
  {
    id: "Q-008",
    title: "Laboratory reissue requested",
    type: "Query",
    site: "S04",
    cut: 8,
    priority: "P2",
    status: "AWAITING RESPONSE",
    action: "Await corrected laboratory data",
    evidence: [
      "Query Q-008 created",
      "Reason: suspected unit mismatch",
      "Clinical escalation not triggered",
    ],
    rationale:
      "The laboratory must confirm or reissue the affected values before they can be trusted.",
  },
  {
    id: "D-015",
    title: "Medical escalation awaiting human decision",
    type: "Human Review",
    site: "S12",
    subject: "SUBJ-204",
    cut: 7,
    priority: "P0",
    status: "PENDING",
    action: "Human approval required",
    evidence: [
      "Serious event detected",
      "Medical rationale available",
      "Human response not yet received",
    ],
    rationale:
      "The escalation is pending human review. An unanswered request does not become approval.",
  },
];

const subjects = [
  ["SUBJ-204", "S12", "Critical AE", "P0", "ESCALATED"],
  ["SUBJ-041", "S04", "GLUC integrity", "P1", "UNTRUSTED"],
  ["SUBJ-087", "S09", "Site integrity", "P1", "REVIEW"],
  ["SUBJ-112", "S07", "Amendment impact", "P2", "RECOMPUTED"],
];

const sites = [
  ["S01", "NORMAL", "Stable", "—"],
  ["S04", "FLAGGED", "Lab distribution shift", "UNTRUSTED"],
  ["S07", "NORMAL", "Amendment impact", "RECOMPUTED"],
  ["S09", "QUARANTINED", "Suspicious regularity", "AUDIT"],
  ["S12", "NORMAL", "Serious event", "MEDICAL REVIEW"],
];

const queries = [
  {
    id: "Q-008",
    subject: "SUBJ-041",
    domain: "Laboratory",
    cut: 8,
    wording: "Please confirm the unit used for GLUC values at S04 during cut 8.",
    status: "AWAITING RESPONSE",
  },
  {
    id: "Q-009",
    subject: "SUBJ-087",
    domain: "Site Integrity",
    cut: 6,
    wording: "Please review the unusually regular observation pattern at S09.",
    status: "OPEN",
  },
];

const cuts = [
  { n: 1, event: "Baseline loaded", type: "normal" },
  { n: 2, event: "Routine monitoring", type: "normal" },
  { n: 3, event: "Human escalation opened", type: "human" },
  { n: 4, event: "No human response", type: "human" },
  { n: 5, event: "Amendment received", type: "amendment" },
  { n: 6, event: "S09 integrity flag", type: "adversarial" },
  { n: 7, event: "Serious AE detected", type: "critical" },
  { n: 8, event: "S04 GLUC unit shift", type: "lab" },
  { n: 9, event: "Protocol modification", type: "document" },
  { n: 10, event: "Standing limits active", type: "human" },
  { n: 11, event: "Safety checks continue", type: "normal" },
  { n: 12, event: "Surveillance complete", type: "normal" },
];

function priorityStyle(priority: Priority) {
  if (priority === "P0")
    return "border-red-400/40 bg-red-400/10 text-red-300";
  if (priority === "P1")
    return "border-orange-400/40 bg-orange-400/10 text-orange-300";
  if (priority === "P2")
    return "border-yellow-400/40 bg-yellow-400/10 text-yellow-300";
  return "border-slate-400/30 bg-slate-400/10 text-slate-300";
}

function priorityLabel(priority: Priority) {
  if (priority === "P0") return "CRITICAL";
  if (priority === "P1") return "HIGH";
  if (priority === "P2") return "MEDIUM";
  return "LOW";
}

function statusStyle(status: string) {
  if (
    ["OPEN", "PENDING", "ESCALATED", "QUARANTINED", "UNTRUSTED"].includes(
      status
    )
  ) {
    return "bg-red-400/10 text-red-300 border-red-400/20";
  }

  if (
    ["AWAITING RESPONSE", "FLAGGED", "REVIEW", "AUDIT"].includes(status)
  ) {
    return "bg-orange-400/10 text-orange-300 border-orange-400/20";
  }

  if (["NORMAL", "RESOLVED", "RECOMPUTED"].includes(status)) {
    return "bg-emerald-400/10 text-emerald-300 border-emerald-400/20";
  }

  return "bg-cyan-400/10 text-cyan-300 border-cyan-400/20";
}

function Badge({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-semibold tracking-wider ${className}`}
    >
      {children}
    </span>
  );
}

function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-2xl border border-white/[0.08] bg-[#10151c]/80 shadow-[0_15px_50px_rgba(0,0,0,0.18)] ${className}`}
    >
      {children}
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <Card className="p-5">
      <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
        {label}
      </div>
      <div className="mt-3 text-3xl font-semibold text-white">{value}</div>
      <div className="mt-2 text-xs text-slate-500">{sub}</div>
    </Card>
  );
}

function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <Badge className={priorityStyle(priority)}>
      {priority} · {priorityLabel(priority)}
    </Badge>
  );
}

export default function Page() {
  const [page, setPage] = useState<Page>("Overview");
  const [selected, setSelected] = useState<Signal | null>(null);
  const [cut, setCut] = useState(8);
  const [human, setHuman] = useState<"PENDING" | "APPROVED" | "REJECTED">(
    "PENDING"
  );
  const [search, setSearch] = useState("");

  const reviewQueue = useMemo(
    () =>
      [...signals].sort((a, b) => {
        const order = { P0: 0, P1: 1, P2: 2, P3: 3 };
        return order[a.priority] - order[b.priority];
      }),
    []
  );

  const filteredSubjects = subjects.filter((s) =>
    s.join(" ").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <main className="min-h-screen bg-[#080b10] text-white">
      <div className="flex min-h-screen">
        {/* SIDEBAR */}
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-white/[0.07] bg-[#0b0f14] px-4 py-5 lg:block">
          <div className="mb-8 flex items-center gap-3 px-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-400/10 text-lg text-cyan-300 ring-1 ring-cyan-400/20">
              ◈
            </div>
            <div>
              <div className="font-semibold tracking-tight">
                Study Sentinel
              </div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">
                Surveillance OS
              </div>
            </div>
          </div>

          <div className="mb-3 px-3 text-[10px] uppercase tracking-[0.2em] text-slate-600">
            Command Center
          </div>

          <nav className="space-y-1">
            {nav.map((item) => (
              <button
                key={item.name}
                onClick={() => setPage(item.name)}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition ${
                  page === item.name
                    ? "bg-cyan-400/10 text-cyan-200 ring-1 ring-cyan-400/10"
                    : "text-slate-400 hover:bg-white/[0.04] hover:text-white"
                }`}
              >
                <span className="w-5 text-center text-sm">{item.icon}</span>
                {item.name}
              </button>
            ))}
          </nav>

          <div className="absolute bottom-5 left-4 right-4">
            <div className="rounded-xl border border-white/[0.07] bg-white/[0.025] p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">System</span>
                <span className="flex items-center gap-2 text-xs text-emerald-300">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  Online
                </span>
              </div>
              <div className="mt-3 text-xs text-slate-500">
                Stage 3 · WATCH
              </div>
              <div className="mt-1 text-xs text-slate-600">
                Current cut: 8 / 12
              </div>
            </div>
          </div>
        </aside>

        {/* CONTENT */}
        <section className="w-full lg:ml-64">
          {/* HEADER */}
          <header className="sticky top-0 z-20 border-b border-white/[0.07] bg-[#080b10]/90 px-5 py-4 backdrop-blur-xl lg:px-8">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs text-slate-500">
                  Study Sentinel / Stage 3
                </div>
                <h1 className="mt-1 text-xl font-semibold">{page}</h1>
              </div>

              <div className="flex items-center gap-3">
                <Badge className="border-emerald-400/20 bg-emerald-400/10 text-emerald-300">
                  ● WATCH ACTIVE
                </Badge>
                <Badge className="border-cyan-400/20 bg-cyan-400/10 text-cyan-300">
                  CUT {cut}/12
                </Badge>
              </div>
            </div>
          </header>

          <div className="mx-auto max-w-[1500px] p-5 lg:p-8">
            {/* OVERVIEW */}
            {page === "Overview" && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-2xl font-semibold">
                    Study health at a glance
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Continuous surveillance across data, safety, integrity and
                    human review.
                  </p>
                </div>

                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
                  <Metric label="Subjects" value="1,248" sub="Across 12 sites" />
                  <Metric label="Sites" value="12" sub="1 quarantined" />
                  <Metric label="Records" value="48.6K" sub="Current period" />
                  <Metric label="Open Reviews" value="7" sub="Prioritized queue" />
                  <Metric
                    label="Human Decisions"
                    value="1"
                    sub="Pending response"
                  />
                </div>

                <Card className="p-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold">12-Cut Surveillance</h3>
                      <p className="mt-1 text-xs text-slate-500">
                        Incremental monitoring timeline
                      </p>
                    </div>
                    <Badge className="border-cyan-400/20 bg-cyan-400/10 text-cyan-300">
                      RUNNING
                    </Badge>
                  </div>

                  <div className="mt-7 grid grid-cols-12 gap-2">
                    {cuts.map((c) => (
                      <button
                        key={c.n}
                        onClick={() => {
                          setCut(c.n);
                          setPage("Surveillance");
                        }}
                        className={`group rounded-xl border p-3 text-center transition ${
                          c.n === cut
                            ? "border-cyan-400/40 bg-cyan-400/10"
                            : "border-white/[0.07] bg-white/[0.02] hover:bg-white/[0.05]"
                        }`}
                      >
                        <div className="text-[10px] text-slate-500">
                          C{c.n}
                        </div>
                        <div
                          className={`mx-auto mt-2 h-2 w-2 rounded-full ${
                            c.type === "critical"
                              ? "bg-red-400"
                              : c.type === "lab"
                                ? "bg-orange-400"
                                : c.type === "adversarial"
                                  ? "bg-yellow-400"
                                  : c.type === "human"
                                    ? "bg-cyan-400"
                                    : "bg-emerald-400"
                          }`}
                        />
                        <div className="mt-2 hidden text-[9px] leading-3 text-slate-500 group-hover:block">
                          {c.event}
                        </div>
                      </button>
                    ))}
                  </div>
                </Card>

                <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
                  <Card className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="font-semibold">Priority Review Queue</h3>
                        <p className="mt-1 text-xs text-slate-500">
                          Highest-risk operational decisions first
                        </p>
                      </div>
                      <button
                        onClick={() => setPage("Review Queue")}
                        className="text-xs text-cyan-300 hover:text-cyan-200"
                      >
                        View all →
                      </button>
                    </div>

                    <div className="mt-5 space-y-2">
                      {reviewQueue.slice(0, 5).map((s) => (
                        <button
                          key={s.id}
                          onClick={() => setSelected(s)}
                          className="flex w-full items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 text-left hover:bg-white/[0.045]"
                        >
                          <PriorityBadge priority={s.priority} />
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-sm font-medium">
                              {s.title}
                            </div>
                            <div className="mt-1 text-xs text-slate-500">
                              {s.id} · {s.site} · Cut {s.cut}
                            </div>
                          </div>
                          <Badge className={statusStyle(s.status)}>
                            {s.status}
                          </Badge>
                        </button>
                      ))}
                    </div>
                  </Card>

                  <Card className="p-6">
                    <h3 className="font-semibold">System Health</h3>

                    <div className="mt-5 space-y-4">
                      {[
                        ["Stage 1", "Data pipeline", "ACTIVE"],
                        ["Stage 2", "Review crew", "ACTIVE"],
                        ["Stage 3", "WATCH", "ACTIVE"],
                        ["Safety checks", "Deterministic", "ACTIVE"],
                        ["Narrative analysis", "Budget-aware", "AVAILABLE"],
                      ].map(([a, b, c]) => (
                        <div
                          key={a}
                          className="flex items-center justify-between border-b border-white/[0.05] pb-3"
                        >
                          <div>
                            <div className="text-sm">{a}</div>
                            <div className="text-xs text-slate-600">{b}</div>
                          </div>
                          <span className="text-[10px] font-semibold tracking-wider text-emerald-300">
                            {c}
                          </span>
                        </div>
                      ))}
                    </div>
                  </Card>
                </div>
              </div>
            )}

            {/* REVIEW QUEUE */}
            {page === "Review Queue" && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-2xl font-semibold">Review Queue</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    All active findings ordered by operational priority.
                  </p>
                </div>

                <div className="grid gap-4 md:grid-cols-4">
                  {(["P0", "P1", "P2", "P3"] as Priority[]).map((p) => {
                    const count = reviewQueue.filter(
                      (x) => x.priority === p
                    ).length;

                    return (
                      <Card key={p} className="p-5">
                        <PriorityBadge priority={p} />
                        <div className="mt-3 text-3xl font-semibold">
                          {count}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {priorityLabel(p)} reviews
                        </div>
                      </Card>
                    );
                  })}
                </div>

                <Card className="overflow-hidden">
                  <div className="border-b border-white/[0.07] p-5">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="font-semibold">All Review Items</h3>
                        <p className="mt-1 text-xs text-slate-500">
                          P0 is immediate safety attention; P1–P3 represent
                          decreasing operational urgency.
                        </p>
                      </div>
                      <Badge className="border-cyan-400/20 bg-cyan-400/10 text-cyan-300">
                        {reviewQueue.length} OPEN ITEMS
                      </Badge>
                    </div>
                  </div>

                  <div className="divide-y divide-white/[0.05]">
                    {reviewQueue.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => setSelected(s)}
                        className="flex w-full items-center gap-4 p-5 text-left hover:bg-white/[0.025]"
                      >
                        <PriorityBadge priority={s.priority} />

                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono text-slate-500">
                              {s.id}
                            </span>
                            <span className="text-sm font-medium">
                              {s.title}
                            </span>
                          </div>
                          <div className="mt-2 text-xs text-slate-500">
                            {s.type} · {s.site} · Cut {s.cut}
                            {s.subject ? ` · ${s.subject}` : ""}
                          </div>
                        </div>

                        <div className="hidden text-right md:block">
                          <div className="text-xs text-slate-600">
                            ACTION
                          </div>
                          <div className="mt-1 text-xs text-slate-300">
                            {s.action}
                          </div>
                        </div>

                        <Badge className={statusStyle(s.status)}>
                          {s.status}
                        </Badge>
                      </button>
                    ))}
                  </div>
                </Card>
              </div>
            )}

            {/* SITES */}
            {page === "Sites" && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-2xl font-semibold">Site Integrity</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Site-level monitoring and adversarial integrity state.
                  </p>
                </div>

                <Card className="overflow-hidden">
                  <div className="grid grid-cols-4 border-b border-white/[0.07] px-5 py-4 text-[10px] uppercase tracking-[0.18em] text-slate-600">
                    <div>Site</div>
                    <div>Status</div>
                    <div>Finding</div>
                    <div>Action</div>
                  </div>

                  {sites.map((s) => (
                    <div
                      key={s[0]}
                      className="grid grid-cols-4 items-center border-b border-white/[0.05] px-5 py-5 last:border-0"
                    >
                      <div className="font-mono text-sm">{s[0]}</div>
                      <div>
                        <Badge className={statusStyle(s[1])}>{s[1]}</Badge>
                      </div>
                      <div className="text-sm text-slate-400">{s[2]}</div>
                      <div className="text-xs text-slate-500">{s[3]}</div>
                    </div>
                  ))}
                </Card>

                <Card className="p-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold">
                        S09 Integrity Lifecycle
                      </h3>
                      <p className="mt-1 text-xs text-slate-500">
                        Suspicious regularity detection
                      </p>
                    </div>
                    <PriorityBadge priority="P1" />
                  </div>

                  <div className="mt-7 flex items-center gap-3">
                    {["FLAGGED", "QUARANTINED", "AUDIT RECOMMENDED"].map(
                      (x, i) => (
                        <div key={x} className="flex items-center gap-3">
                          <div
                            className={`rounded-xl border px-4 py-3 text-xs ${
                              i === 1
                                ? "border-orange-400/30 bg-orange-400/10 text-orange-300"
                                : "border-white/[0.07] text-slate-400"
                            }`}
                          >
                            {x}
                          </div>
                          {i < 2 && (
                            <span className="text-slate-700">→</span>
                          )}
                        </div>
                      )
                    )}
                  </div>
                </Card>
              </div>
            )}

            {/* SUBJECTS */}
            {page === "Subjects" && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-2xl font-semibold">Subjects</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Subject-level safety and integrity findings.
                  </p>
                </div>

                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search subject, site or finding..."
                  className="w-full rounded-xl border border-white/[0.08] bg-[#10151c] px-4 py-3 text-sm outline-none placeholder:text-slate-600 focus:border-cyan-400/30"
                />

                <Card className="overflow-hidden">
                  <div className="grid grid-cols-5 border-b border-white/[0.07] px-5 py-4 text-[10px] uppercase tracking-[0.18em] text-slate-600">
                    <div>Subject</div>
                    <div>Site</div>
                    <div>Finding</div>
                    <div>Priority</div>
                    <div>Status</div>
                  </div>

                  {filteredSubjects.map((s) => (
                    <div
                      key={s[0]}
                      className="grid grid-cols-5 items-center border-b border-white/[0.05] px-5 py-5 last:border-0"
                    >
                      <div className="font-mono text-xs">{s[0]}</div>
                      <div className="text-sm text-slate-400">{s[1]}</div>
                      <div className="text-sm">{s[2]}</div>
                      <div>
                        <PriorityBadge priority={s[3] as Priority} />
                      </div>
                      <div>
                        <Badge className={statusStyle(s[4])}>{s[4]}</Badge>
                      </div>
                    </div>
                  ))}
                </Card>
              </div>
            )}

            {/* QUERIES */}
            {page === "Queries" && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-2xl font-semibold">Query Center</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Open questions and external responses.
                  </p>
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                  <Metric label="Open" value="2" sub="Awaiting response" />
                  <Metric label="Closed" value="14" sub="This surveillance period" />
                  <Metric label="Duplicates Skipped" value="3" sub="Deduplicated automatically" />
                </div>

                <Card className="overflow-hidden">
                  {queries.map((q) => (
                    <div
                      key={q.id}
                      className="border-b border-white/[0.05] p-5 last:border-0"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs text-cyan-300">
                              {q.id}
                            </span>
                            <Badge className="border-white/[0.08] text-slate-400">
                              {q.domain}
                            </Badge>
                          </div>

                          <div className="mt-3 text-sm">{q.wording}</div>

                          <div className="mt-2 text-xs text-slate-600">
                            {q.subject} · Cut {q.cut}
                          </div>
                        </div>

                        <Badge className={statusStyle(q.status)}>
                          {q.status}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </Card>
              </div>
            )}

            {/* HUMAN GATE */}
            {page === "Human Gate" && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-2xl font-semibold">Human Decision Center</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Humans remain in control of approval-gated actions.
                  </p>
                </div>

                <Card className="p-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs text-slate-600">
                        DECISION D-015
                      </div>
                      <h3 className="mt-2 text-xl font-semibold">
                        Medical escalation · SUBJ-204
                      </h3>
                      <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
                        Serious adverse event detected at cut 7. Medical
                        rationale is available. Human response is required.
                      </p>
                    </div>

                    <PriorityBadge priority="P0" />
                  </div>

                  <div className="mt-7 grid gap-4 md:grid-cols-3">
                    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
                      <div className="text-[10px] uppercase tracking-wider text-slate-600">
                        Response
                      </div>
                      <div className="mt-2 text-lg font-semibold">
                        {human}
                      </div>
                    </div>

                    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
                      <div className="text-[10px] uppercase tracking-wider text-slate-600">
                        Pending
                      </div>
                      <div className="mt-2 text-lg font-semibold">
                        Cut 3 → Cut 7
                      </div>
                    </div>

                    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
                      <div className="text-[10px] uppercase tracking-wider text-slate-600">
                        Standing Limits
                      </div>
                      <div className="mt-2 text-lg font-semibold text-emerald-300">
                        ACTIVE
                      </div>
                    </div>
                  </div>

                  <div className="mt-6 rounded-xl border border-cyan-400/10 bg-cyan-400/[0.04] p-4 text-sm text-cyan-100">
                    <strong>UNANSWERED ≠ APPROVED.</strong> The system
                    continues only within configured standing limits.
                  </div>

                  <div className="mt-6 flex flex-wrap gap-3">
                    <button
                      onClick={() => setHuman("APPROVED")}
                      className="rounded-xl bg-emerald-400/15 px-5 py-3 text-sm font-medium text-emerald-300 ring-1 ring-emerald-400/20 hover:bg-emerald-400/20"
                    >
                      APPROVE
                    </button>

                    <button
                      onClick={() => setHuman("REJECTED")}
                      className="rounded-xl bg-red-400/10 px-5 py-3 text-sm font-medium text-red-300 ring-1 ring-red-400/20 hover:bg-red-400/15"
                    >
                      REJECT
                    </button>

                    <button
                      onClick={() => setHuman("PENDING")}
                      className="rounded-xl bg-cyan-400/10 px-5 py-3 text-sm font-medium text-cyan-300 ring-1 ring-cyan-400/20 hover:bg-cyan-400/15"
                    >
                      CLARIFY / RESET
                    </button>
                  </div>
                </Card>
              </div>
            )}

            {/* SURVEILLANCE */}
            {page === "Surveillance" && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-2xl font-semibold">
                    Surveillance Timeline
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Inspect each cut and its recorded system activity.
                  </p>
                </div>

                <Card className="p-6">
                  <div className="grid grid-cols-12 gap-2">
                    {cuts.map((c) => (
                      <button
                        key={c.n}
                        onClick={() => setCut(c.n)}
                        className={`rounded-xl border p-4 text-center ${
                          cut === c.n
                            ? "border-cyan-400/40 bg-cyan-400/10"
                            : "border-white/[0.07] bg-white/[0.02]"
                        }`}
                      >
                        <div className="text-xs text-slate-500">
                          CUT {c.n}
                        </div>
                        <div className="mt-2 text-xs font-medium">
                          {c.event}
                        </div>
                      </button>
                    ))}
                  </div>
                </Card>

                <Card className="p-6">
                  <div className="text-xs uppercase tracking-wider text-slate-600">
                    SELECTED CUT
                  </div>
                  <div className="mt-2 text-2xl font-semibold">CUT {cut}</div>

                  <div className="mt-6 space-y-3">
                    {signals
                      .filter((s) => s.cut === cut)
                      .map((s) => (
                        <button
                          key={s.id}
                          onClick={() => setSelected(s)}
                          className="flex w-full items-center gap-4 rounded-xl border border-white/[0.07] bg-white/[0.02] p-4 text-left"
                        >
                          <PriorityBadge priority={s.priority} />
                          <div className="flex-1">
                            <div className="text-sm font-medium">
                              {s.title}
                            </div>
                            <div className="mt-1 text-xs text-slate-500">
                              {s.id} · {s.action}
                            </div>
                          </div>
                        </button>
                      ))}

                    {signals.filter((s) => s.cut === cut).length === 0 && (
                      <div className="rounded-xl border border-white/[0.06] p-6 text-sm text-slate-500">
                        No active review findings recorded for this cut.
                      </div>
                    )}
                  </div>
                </Card>
              </div>
            )}

            {/* AUDIT TRAIL */}
            {page === "Audit Trail" && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-2xl font-semibold">Audit Trail</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Trace-backed record of surveillance decisions.
                  </p>
                </div>

                <Card className="p-6">
                  <div className="space-y-0">
                    {[
                      ["08:42:11", "Detect", "D-008", "Lab distribution shift"],
                      ["08:42:13", "Medical Review", "D-008", "Clinical context checked"],
                      ["08:42:15", "Data Manager", "D-008", "Values marked UNTRUSTED"],
                      ["08:42:17", "Compliance", "D-008", "Safety exclusion recorded"],
                      ["08:42:19", "Human Gate", "D-008", "No medical escalation"],
                      ["08:42:21", "Execute", "Q-008", "Laboratory query created"],
                    ].map((e, i) => (
                      <div
                        key={i}
                        className="relative flex gap-4 border-l border-white/[0.08] pb-7 pl-6 last:pb-0"
                      >
                        <div className="absolute -left-[5px] top-0 h-2.5 w-2.5 rounded-full bg-cyan-400 ring-4 ring-[#10151c]" />

                        <div className="w-20 shrink-0 font-mono text-[10px] text-slate-600">
                          {e[0]}
                        </div>

                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">
                              {e[1]}
                            </span>
                            <span className="font-mono text-xs text-cyan-300">
                              {e[2]}
                            </span>
                          </div>
                          <div className="mt-1 text-xs text-slate-500">
                            {e[3]}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>

                <Card className="p-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold">Trace Viewer · D-008</h3>
                      <p className="mt-1 text-xs text-slate-500">
                        Laboratory integrity decision
                      </p>
                    </div>

                    <Badge className="border-emerald-400/20 bg-emerald-400/10 text-emerald-300">
                      TRACE CONSISTENT
                    </Badge>
                  </div>

                  <div className="mt-6 grid gap-3 md:grid-cols-6">
                    {[
                      "DETECT",
                      "MEDICAL REVIEW",
                      "DATA MANAGER",
                      "COMPLIANCE",
                      "HUMAN GATE",
                      "EXECUTE",
                    ].map((x, i) => (
                      <div
                        key={x}
                        className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4"
                      >
                        <div className="text-[10px] text-cyan-300">
                          0{i + 1}
                        </div>
                        <div className="mt-2 text-xs font-medium leading-4">
                          {x}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-6 rounded-xl border border-white/[0.07] bg-black/20 p-5">
                    <div className="text-[10px] uppercase tracking-wider text-slate-600">
                      WHY
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-400">
                      The observed GLUC distribution changed by approximately
                      the textbook mg/dL ↔ mmol/L conversion factor. The system
                      therefore treated the values as untrusted laboratory
                      data, excluded them from safety analysis and queried the
                      laboratory instead of escalating a clinical emergency.
                    </p>
                  </div>
                </Card>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* DETAIL MODAL */}
      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-5 backdrop-blur-sm"
          onClick={() => setSelected(null)}
        >
          <div
            className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-2xl border border-white/[0.09] bg-[#0d1218] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="border-b border-white/[0.07] p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-cyan-300">
                      {selected.id}
                    </span>
                    <PriorityBadge priority={selected.priority} />
                    <Badge className={statusStyle(selected.status)}>
                      {selected.status}
                    </Badge>
                  </div>

                  <h2 className="mt-3 text-xl font-semibold">
                    {selected.title}
                  </h2>

                  <p className="mt-2 text-sm text-slate-500">
                    {selected.type} · {selected.site} · Cut {selected.cut}
                  </p>
                </div>

                <button
                  onClick={() => setSelected(null)}
                  className="rounded-lg px-3 py-2 text-slate-500 hover:bg-white/[0.05] hover:text-white"
                >
                  ✕
                </button>
              </div>
            </div>

            <div className="space-y-6 p-6">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-slate-600">
                  Action
                </div>
                <div className="mt-2 text-sm text-slate-300">
                  {selected.action}
                </div>
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-slate-600">
                  Evidence
                </div>
                <div className="mt-3 space-y-2">
                  {selected.evidence.map((e) => (
                    <div
                      key={e}
                      className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3 text-sm text-slate-400"
                    >
                      {e}
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-slate-600">
                  Rationale
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  {selected.rationale}
                </p>
              </div>

              <div className="rounded-xl border border-cyan-400/10 bg-cyan-400/[0.035] p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium">
                      Trace available
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      Decision evidence can be inspected in Audit Trail.
                    </div>
                  </div>

                  <button
                    onClick={() => {
                      setSelected(null);
                      setPage("Audit Trail");
                    }}
                    className="rounded-lg bg-cyan-400/10 px-4 py-2 text-xs font-medium text-cyan-300 ring-1 ring-cyan-400/20"
                  >
                    View Trace →
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}