"""
CareerPilot — Pipeline
=======================
Main entrypoint that wires all three agents together, starts the message bus,
and runs the async event loop.

Usage
-----
  python -m orchestration.pipeline                     # interactive REPL
  python -m orchestration.pipeline --goal "Apply to 10 ML roles"
  python -m orchestration.pipeline --demo              # demo mode with mock data
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys

import structlog

from agents.commander import CommanderAgent
from agents.predictor import PredictorAgent
from agents.tracker import TrackerAgent
from core.message_bus import get_bus

# Import tools package to auto-register all tools
import tools  # noqa: F401

logger = structlog.get_logger(__name__)


# ── Logging setup ─────────────────────────────────────────────────────────────

def _configure_logging(level: str = "INFO") -> None:
    """Configure structlog for human-readable development output."""
    import logging
    import structlog

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level, logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


# ── Pipeline class ─────────────────────────────────────────────────────────────

class CareerPilotPipeline:
    """
    Assembles and manages the full multi-agent pipeline.

    Lifecycle
    ---------
    1. start()  — boot bus + all agents
    2. run_goal() — submit a user goal to the Commander
    3. stop()   — graceful shutdown
    """

    def __init__(self) -> None:
        self._bus = get_bus()
        self.commander = CommanderAgent(bus=self._bus)
        self.tracker = TrackerAgent(bus=self._bus)
        self.predictor = PredictorAgent(bus=self._bus)
        self._agents = [self.commander, self.tracker, self.predictor]
        self._running = False

    async def start(self) -> None:
        """Start the message bus and all agents."""
        logger.info("pipeline.starting")
        await self._bus.start()
        for agent in self._agents:
            await agent.start()
        self._running = True
        logger.info(
            "pipeline.ready",
            agents=[a.agent_id for a in self._agents],
            tools=len(self._bus.stats()["subscriptions"]),
        )

    async def stop(self) -> None:
        """Gracefully stop all agents and the message bus."""
        logger.info("pipeline.stopping")
        for agent in reversed(self._agents):
            await agent.stop()
        await self._bus.stop()
        self._running = False
        logger.info("pipeline.stopped")

    async def run_goal(self, goal: str) -> None:
        """Submit a high-level goal to the Commander and await completion."""
        if not self._running:
            raise RuntimeError("Pipeline is not started. Call start() first.")
        logger.info("pipeline.goal_submitted", goal=goal)
        await self.commander.run_goal(goal)
        # Give agents time to process and propagate messages
        await asyncio.sleep(3)

    async def run_demo(self) -> None:
        """
        Run a full demonstration flow with mock data.
        Shows all three agents collaborating end-to-end.
        """
        logger.info("pipeline.demo_starting")

        # Step 1: Sync profile
        logger.info("demo.step_1", action="Syncing LinkedIn profile + email inbox")
        await self.commander.run_goal("Sync my LinkedIn profile and check my email for recruiter messages")
        await asyncio.sleep(4)

        # Step 2: Search jobs
        logger.info("demo.step_2", action="Searching for ML/AI roles")
        await self.commander.run_goal("Find 20 Machine Learning Engineer jobs in Remote and Bangalore")
        await asyncio.sleep(8)

        # Step 3: Score and recommend
        logger.info("demo.step_3", action="Scoring all jobs and generating recommendations")
        await self.commander.run_goal("Score all discovered jobs and show me the top 5 matches")
        await asyncio.sleep(6)

        # Step 4: Weekly report — use a real AgentMessage
        logger.info("demo.step_4", action="Generating weekly report")
        from models.schemas import AgentMessage, MessageType
        report_msg = AgentMessage(
            sender="pipeline",
            recipient="predictor",
            topic="predictions",
            type=MessageType.TASK,
            payload={"action": "generate_report", "params": {}},
        )
        await self.predictor._handle_generate_report(report_msg)
        await asyncio.sleep(2)


        # Print summary
        print("\n" + "─" * 60)
        print("🎯  CareerPilot Demo Complete")
        print("─" * 60)
        print(f"  Commander goals processed : {self.commander._goal_count}")
        print(f"  Jobs discovered           : {len(self.tracker._known_job_keys)}")
        print(f"  Jobs scored               : {len(self.predictor._scored_job_ids)}")
        bus_stats = self._bus.stats()
        print(f"  Messages dispatched       : {bus_stats['total_messages_dispatched']}")
        print("─" * 60)

        top = await self.predictor.get_top_recommendations(n=3)
        if top:
            print("\n🏆  Top 3 Job Recommendations:")
            for i, rec in enumerate(top, 1):
                print(f"\n  {i}. {rec.job_title} @ {rec.company}")
                print(f"     Fit Score       : {rec.fit_score:.0f}/100")
                print(f"     Response Prob   : {rec.response_probability:.0%}")
                print(f"     Recommendation  : {rec.recommendation}")
                print(f"     Matched Skills  : {', '.join(rec.matched_skills[:4]) or 'N/A'}")
                print(f"     Missing Skills  : {', '.join(rec.missing_skills[:3]) or 'None'}")
        print()

    def status(self) -> dict[str, object]:
        """Return a combined status dict from all agents."""
        return {
            "pipeline": {"running": self._running},
            "bus": self._bus.stats(),
            "commander": self.commander.status(),
            "tracker": self.tracker.status(),
            "predictor": self.predictor.status(),
        }


# ── Signal handling ────────────────────────────────────────────────────────────

_pipeline_ref: CareerPilotPipeline | None = None


def _handle_shutdown(sig: int, frame: object) -> None:
    logger.info("pipeline.signal_received", signal=sig)
    if _pipeline_ref:
        asyncio.get_event_loop().create_task(_pipeline_ref.stop())
    sys.exit(0)


# ── CLI entrypoint ────────────────────────────────────────────────────────────

async def _main(goal: str | None = None, demo: bool = False) -> None:
    global _pipeline_ref

    from core.config import settings
    _configure_logging(settings.log_level)

    pipeline = CareerPilotPipeline()
    _pipeline_ref = pipeline

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    await pipeline.start()

    try:
        if demo:
            await pipeline.run_demo()
        elif goal:
            await pipeline.run_goal(goal)
        else:
            # Interactive REPL
            print("\n🚀  CareerPilot is running. Type a goal and press Enter.")
            print("    Type 'quit' to exit, 'status' to see agent states.\n")
            while True:
                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, input, "careerpilot> "
                    )
                    user_input = user_input.strip()
                    if not user_input:
                        continue
                    if user_input.lower() in ("quit", "exit", "q"):
                        break
                    if user_input.lower() == "status":
                        import json
                        print(json.dumps(pipeline.status(), indent=2, default=str))
                        continue
                    await pipeline.run_goal(user_input)
                except (EOFError, KeyboardInterrupt):
                    break
    finally:
        await pipeline.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="CareerPilot Multi-Agent System")
    parser.add_argument("--goal", type=str, help="Single goal to execute then exit")
    parser.add_argument("--demo", action="store_true", help="Run a full demo flow")
    args = parser.parse_args()

    asyncio.run(_main(goal=args.goal, demo=args.demo))


if __name__ == "__main__":
    main()
