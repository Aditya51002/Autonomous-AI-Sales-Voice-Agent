"""Runs scripted calls through live analysis and compares the lead grade.

Run from the project root:  python -m scripts.eval_qualification
Makes one billed Gemini request per caller turn.
"""

import asyncio
import json
import statistics
import time

from apps.agent import providers
from packages.core.config import ROOT, get_settings
from packages.core.leads.models import LeadFacts
from packages.core.leads.scoring import score_lead
from packages.core.leads.state import merge


async def main() -> None:
    settings = get_settings()
    settings.require("gemini_api_key")
    client = providers.build_analysis_client(settings)
    analyze = providers.build_analyzer(settings, client)
    calls = json.loads((ROOT / "evals" / "qualification.json").read_text())
    matched, times, failures = 0, [], 0
    try:
        for call in calls:
            print(f"\n{call['name']}")
            facts = LeadFacts()
            for agent_said, caller in call["turns"]:
                request = json.dumps(
                    {
                        "agent_said_before": agent_said,
                        "caller_new_message": caller,
                        "already_known": facts.model_dump(exclude_none=True),
                    },
                    ensure_ascii=False,
                )
                started = time.perf_counter()
                try:
                    found = await analyze(request)
                except Exception as error:
                    failures += 1
                    print(f"  failed: {type(error).__name__} {getattr(error, 'code', '')}")
                    continue
                times.append(time.perf_counter() - started)
                facts, changed = merge(facts, found, caller)
                offered = [
                    n for n in ("need", "budget", "authority", "timeline") if getattr(found, n)
                ]
                dropped = [n for n in offered if n not in changed]
                note = f", not accepted: {', '.join(dropped)}" if dropped else ""
                print(
                    f"  {found.sentiment.label:8s} score {score_lead(facts, settings.min_monthly_budget_inr).total:3d}"
                    f"  updated: {', '.join(changed) or '-'}{note}"
                )
            result = score_lead(facts, settings.min_monthly_budget_inr)
            ok = result.grade == call["expected_grade"]
            matched += ok
            print(
                f"  => {result.grade} {result.total} (expected {call['expected_grade']})"
                f" {'OK' if ok else 'MISMATCH'}  {result.points}"
            )
    finally:
        await client.aio.aclose()
    print(f"\ngrades matched: {matched}/{len(calls)}, failed requests: {failures}")
    if times:
        print(f"analysis time: median {statistics.median(times):.1f} s, worst {max(times):.1f} s")


if __name__ == "__main__":
    asyncio.run(main())
