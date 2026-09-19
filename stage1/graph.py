"""
Owned by: Person C
Builds a simple graph: subject nodes, site nodes, and edges for every
domain record a subject has. This is what a flat table join wouldn't give
you directly: fast "everything about subject X" and "everything at site Y"
traversal, plus subject-to-subject comparison within the same site.

Keep this simple. A dict-of-dicts adjacency structure is fine — you are not
graded on graph sophistication, you're graded on it working and on
build() returning real stats.
"""
import json


def build(data):
    """
    data: the dict from loader.load_data() (optionally cut-filtered).
    Returns: (graph, stats)
      graph: {
        "subjects": {usubjid: {"site": siteid, "records": {domain: [rec,...]}}},
        "sites": {siteid: [usubjid, ...]}
      }
      stats: a flat dict suitable for graph_stats.json
    """
    graph = {"subjects": {}, "sites": {}}

    for dm_row in data.get("DM", []):
        usubjid = dm_row["USUBJID"]
        site = dm_row["SITEID"]
        graph["subjects"][usubjid] = {"site": site, "demographics": dm_row, "records": {}}
        graph["sites"].setdefault(site, []).append(usubjid)

    for domain, records in data.items():
        if domain == "DM":
            continue
        for r in records:
            usubjid = r.get("USUBJID")
            subj = graph["subjects"].get(usubjid)
            if subj is None:
                continue  # record for a subject not in DM — note this as a finding upstream
            subj["records"].setdefault(domain, []).append(r)

    stats = {
        "n_subjects": len(graph["subjects"]),
        "n_sites": len(graph["sites"]),
        "records_per_domain": {
            domain: len(records) for domain, records in data.items()
        },
        "subjects_per_site": {
            site: len(subjects) for site, subjects in graph["sites"].items()
        },
    }
    return graph, stats

def trace_subject(graph, usubjid):
    """
    Trace all graph connections for one subject.

    Returns a simple path-like structure showing:
    Subject -> Site -> Domain -> Record
    """
    subject = graph["subjects"].get(usubjid)

    if subject is None:
        return {
            "subject": usubjid,
            "found": False,
            "trace": []
        }

    trace = [
        {
            "type": "SUBJECT",
            "id": usubjid
        },
        {
            "type": "SITE",
            "id": subject["site"]
        }
    ]

    for domain, records in subject["records"].items():
        for record in records:
            seq_field = f"{domain}SEQ"

            trace.append({
                "type": "RECORD",
                "domain": domain,
                "seq": record.get(seq_field, ""),
                "subject": record.get("USUBJID", usubjid)
            })

    return {
        "subject": usubjid,
        "found": True,
        "trace": trace
    }

def trace_evidence(graph, evidence):
    """
    Trace a specific evidence path.

    evidence format:
    [domain, usubjid, sequence]
    """
    path = []

    for domain, usubjid, seq in evidence:
        subject = graph["subjects"].get(usubjid)

        if subject is None:
            continue

        path.append({
            "subject": usubjid,
            "site": subject["site"],
            "domain": domain,
            "seq": str(seq)
        })

    return path

def write_stats(stats, out_path="graph_stats.json"):
    with open(out_path, "w") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    from loader import load_data
    data = load_data("hackathon-data")
    graph, stats = build(data)
    write_stats(stats)
    print(json.dumps(stats, indent=2))
