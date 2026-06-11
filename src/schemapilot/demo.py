"""The canonical 3-source demo corpus (FILE_1 §3.2's collision scenario) and
a CLI that runs the full pipeline on it.

    python -m schemapilot.demo [out_dir]

The corpus reproduces the Mohammed Al-Rashid scenario at known ground truth:
three sources, every field in conflict, one person — plus a second entity
carrying a GDPR-erased phone, a sentinel date, and re-ingestion bait.
"""
from __future__ import annotations

import sys
from pathlib import Path

from schemapilot.layer0_ingestion.connectors import SourceDeclaration
from schemapilot.layer2_alignment.cco import CCO, seed_person_cco
from schemapilot.pipeline import PipelineResult, SourceInput, run

EXTRACTION_TS = "2024-06-15T00:00:00Z"  # pinned: determinism (A8)

CRM_CSV = (
    "Customer_ID,Name,DOB,Phone,Email,Address,Status\n"
    "C-1001,Mohammed Al-Rashid,1985-03-04,+966 50 111 2222,m.alrashid@example.com,\"Riyadh, Olaya St.\",ACTIVE\n"
    "C-1002,Sara Hassan,1990-07-21,+966 55 333 4444,sara.h@example.com,Jeddah,ACTIVE\n"
    "C-1003,Omar Khalil,1900-01-01,+966 56 777 8888,omar.k@example.com,Dammam,ACTIVE\n"
).encode("utf-8")

BILLING_CSV = (
    "Client_ID,Full_Name,Birth_Date,Mobile,Email,Home_Address,Account_Status\n"
    "B-77,Mohamed Alrashid,1985-04-03,+966 50 999 8888,m.alrashid@example.com,\"Jeddah, Corniche Rd.\",CHURNED\n"
    "B-78,Sara Hassan,1990-07-21,ERASED,sara.h@example.com,Jeddah,ACTIVE\n"
).encode("utf-8")

LEGACY_CSV = (
    "ID,الاسم,تاريخ الميلاد,الهاتف,Email,العنوان,الحالة\n"
    "L-5,محمد الراشد,04/03/1985,050 111 2222,m.alrashid@example.com,الرياض، شارع العليا,active\n"
    "L-6,عمر خليل,02/11/1978,056 777 8888,omar.k@example.com,الدمام,active\n"
).encode("utf-8")


def canonical_inputs() -> list[SourceInput]:
    return [
        SourceInput(
            CRM_CSV,
            SourceDeclaration("crm", locale="en_GB", timezone="Asia/Riyadh",
                              asserted_time="2024-01-15T09:00:00Z"),
            "batch-crm-2024-01",
            extraction_timestamp=EXTRACTION_TS,
        ),
        SourceInput(
            BILLING_CSV,
            SourceDeclaration("billing", locale="en_US", timezone="Asia/Riyadh",
                              asserted_time="2024-06-10T14:00:00Z"),
            "batch-billing-2024-06",
            extraction_timestamp=EXTRACTION_TS,
        ),
        SourceInput(
            LEGACY_CSV,
            SourceDeclaration("legacy", locale="ar_SA", timezone="Asia/Riyadh",
                              asserted_time="2019-03-01T08:00:00Z"),
            "batch-legacy-2019",
            extraction_timestamp=EXTRACTION_TS,
        ),
    ]


def run_demo(out_dir: Path | str, cco: CCO | None = None) -> PipelineResult:
    return run(canonical_inputs(), cco or seed_person_cco(), out_dir)


def main(argv: list[str]) -> int:
    out_dir = Path(argv[1]) if len(argv) > 1 else Path("./schemapilot-demo-out")
    result = run_demo(out_dir)

    print(f"SSOT artifact: {result.artifact_dir}\n")
    print(f"{len(result.golden)} golden entities from {len(result.records)} source records")
    print(f"routing census: {result.routing.census()}")
    print(f"drift events: {len(result.drift_events)}; open adjudications: {result.queue.open_count}\n")

    for g in result.golden:
        members = ", ".join(g.member_record_ids)
        print(f"── {g.cluster_id}  (stability {g.cluster_stability}, members: {members})")
        for concept_id, cert in sorted(result.certified[g.cluster_id].items()):
            cell = cert.cell
            from schemapilot.layer6_certification.ssot import _render

            value = _render(cell.value)
            extra = " ESCALATED" if cell.escalated else ""
            print(f"   {concept_id:26} = {value:35} [{cert.tier.value:11}] "
                  f"trust={cert.trust:.3f} via {cell.winning_strategy}{extra}")
        print()
    if result.ledger:
        print("conflict ledger:")
        for e in result.ledger:
            print(f"   {e.cluster_id}/{e.concept_id}: {e.losing_value!r} "
                  f"({','.join(e.sources)}) lost to {e.winning_value!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
