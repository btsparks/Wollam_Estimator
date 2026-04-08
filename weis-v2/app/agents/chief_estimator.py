"""Chief Estimator Agent — aggregates all sub-agent reports into a unified brief.

This agent does NOT do its own document analysis. It reads the reports
from the other agents and produces a combined intelligence summary
organized by SOV item.
"""

from __future__ import annotations

import json
import logging
import time

from app.agents.base import BaseAgent, AgentReport
from app.database import get_connection

logger = logging.getLogger(__name__)


class ChiefEstimatorAgent(BaseAgent):
    name = "chief_estimator"
    display_name = "Chief Estimator Brief"
    version = "1.0"
    system_prompt = ""  # Not used — this agent aggregates, not analyzes

    def run(
        self,
        bid_id: int,
        doc_chunks: list[dict],
        context: dict,
    ) -> AgentReport:
        """Aggregate sub-agent reports into a unified brief."""
        start = time.time()
        report = AgentReport(
            agent_name=self.name,
            input_doc_count=0,
            input_chunk_count=0,
        )

        try:
            # Load all sub-agent reports
            conn = get_connection()
            try:
                rows = conn.execute(
                    """SELECT agent_name, status, report_json, risk_rating,
                              flags_count, summary_text
                       FROM agent_reports
                       WHERE bid_id = ? AND agent_name != 'chief_estimator'""",
                    (bid_id,),
                ).fetchall()
            finally:
                conn.close()

            if not rows:
                report.summary_text = "No sub-agent reports available. Run individual agents first."
                report.report_json = self._empty_report()
                report.duration_seconds = time.time() - start
                return report

            # Aggregate
            sub_reports = {}
            all_flags = []
            highest_risk = "low"
            risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}

            for row in rows:
                name = row["agent_name"]
                parsed = {}
                if row["report_json"]:
                    try:
                        parsed = json.loads(row["report_json"])
                    except json.JSONDecodeError:
                        parsed = {}

                sub_reports[name] = {
                    "status": row["status"],
                    "risk_rating": row["risk_rating"],
                    "flags_count": row["flags_count"],
                    "summary": row["summary_text"],
                    "report": parsed,
                }

                # Collect all flags
                flags = parsed.get("flags", [])
                for flag in flags:
                    all_flags.append({"source": name, "flag": flag})

                # Track highest risk
                r = row["risk_rating"] or "low"
                if risk_order.get(r, 0) > risk_order.get(highest_risk, 0):
                    highest_risk = r

            # Build SOV-organized view
            sov_intel = self._organize_by_sov(context.get("sov_items", []), sub_reports)

            report.report_json = {
                "sub_reports": {
                    name: {
                        "status": sr["status"],
                        "risk_rating": sr["risk_rating"],
                        "summary": sr["summary"],
                    }
                    for name, sr in sub_reports.items()
                },
                "all_flags": all_flags,
                "sov_intelligence": sov_intel,
                "overall_risk": highest_risk,
            }

            report.risk_rating = highest_risk
            report.flags_count = len(all_flags)
            report.summary_text = self._build_summary(report.report_json)

        except Exception as e:
            logger.error("Chief estimator failed for bid %d: %s", bid_id, e)
            report.status = "error"
            report.error_message = str(e)

        report.duration_seconds = time.time() - start
        return report

    def _organize_by_sov(self, sov_items: list[dict], sub_reports: dict) -> list[dict]:
        """Cross-reference sub-agent findings with SOV items."""
        sov_intel = []
        for item in sov_items:
            item_num = item.get("item_number", "")
            item_desc = item.get("description", "")
            intel = {
                "item_number": item_num,
                "description": item_desc,
                "findings": [],
            }

            # Check each agent's findings for references to this SOV item
            for agent_name, sr in sub_reports.items():
                rpt = sr.get("report", {})

                # Document control — addendum changes
                for change in rpt.get("addendum_changes", []):
                    affected = change.get("affected_sov_items", [])
                    if item_num in affected or any(item_num in str(a) for a in affected):
                        intel["findings"].append({
                            "source": agent_name,
                            "type": "addendum_change",
                            "detail": change.get("changes", ""),
                        })

                # QA/QC — testing requirements
                for test in rpt.get("testing_requirements", []):
                    affected = test.get("affected_sov_items", [])
                    if item_num in affected or any(item_num in str(a) for a in affected):
                        intel["findings"].append({
                            "source": agent_name,
                            "type": "testing_requirement",
                            "detail": f"{test.get('test', '')} — {test.get('frequency', '')}",
                        })

                # Subcontract — scope assignments
                for scope in rpt.get("recommended_sub_scopes", []):
                    if item_num in scope.get("sov_items", []):
                        intel["findings"].append({
                            "source": agent_name,
                            "type": "subcontract_scope",
                            "detail": f"Sub to {scope.get('discipline', '?')}: {scope.get('scope_summary', '')}",
                        })

                for scope in rpt.get("self_perform_recommended", []):
                    if item_num in scope.get("sov_items", []):
                        intel["findings"].append({
                            "source": agent_name,
                            "type": "self_perform",
                            "detail": f"Self-perform ({scope.get('discipline', '?')}): {scope.get('reason', '')}",
                        })

            if intel["findings"]:
                sov_intel.append(intel)

        return sov_intel

    def _build_summary(self, report_json: dict) -> str:
        sub = report_json.get("sub_reports", {})
        flags = report_json.get("all_flags", [])
        risk = report_json.get("overall_risk", "low")

        parts = [f"{len(sub)} agent(s) aggregated"]
        if flags:
            parts.append(f"{len(flags)} total flag(s)")
        parts.append(f"overall risk: {risk}")
        return ". ".join(parts) + "."

    def _empty_report(self) -> dict:
        return {
            "sub_reports": {},
            "all_flags": [],
            "sov_intelligence": [],
            "overall_risk": "low",
        }
