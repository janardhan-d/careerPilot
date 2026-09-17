"""
CareerPilot — Commander Agent
==============================
The central orchestrator. Receives high-level user goals, decomposes them
into tasks via LLM, delegates to Tracker and Predictor, and aggregates
results into actionable reports.

Subscribed topics: commands
Publishes to:      jobs (task), predictions (task), events

Message handling
----------------
  TASK  → decompose goal → spawn subtasks → delegate
  RESULT → aggregate partial results
  EVENT → log and react (e.g. new jobs found → trigger predictions)
  ERROR → log, retry once, then escalate
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from agents.base_agent import BaseAgent
from core.config import settings
from models.schemas import (
    AgentMessage,
    GoalInput,
    MessagePriority,
    MessageType,
    WeeklyReport,
)

logger = structlog.get_logger(__name__)

COMMANDER_SYSTEM_PROMPT = """
You are CareerPilot Commander, an AI orchestrator managing a job search pipeline.
Your job is to decompose high-level career goals into concrete tasks for two agents:
  - tracker: discovers and tracks job postings, manages application status
  - predictor: scores jobs for fit, predicts success probability, recommends actions

Given a goal, respond with a JSON object:
{
  "tracker_tasks": [
    {"action": "search_jobs", "params": {"query": "...", "location": "...", "max_results": 20}},
    ...
  ],
  "predictor_tasks": [
    {"action": "score_all_pending", "params": {}},
    ...
  ],
  "insights": ["...key observation..."]
}

Be precise. Only include tasks that the agents can actually perform.
""".strip()


class CommanderAgent(BaseAgent):
    """
    🧠 Commander — Orchestrates the entire job search pipeline.

    Responsibilities
    ----------------
    1. Accept user goals via the 'commands' topic.
    2. Break goals into subtasks using LLM.
    3. Delegate tasks to Tracker and Predictor.
    4. Aggregate results and expose a status summary.
    5. React to agent events (new jobs, new predictions).
    """

    agent_id = "commander"
    subscribed_topics = ["commands", "events"]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pending_results: dict[str, list[dict[str, Any]]] = {}
        self._goal_count = 0
        self._latest_report: WeeklyReport | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def on_start(self) -> None:
        self._log.info("commander.ready")

    # ── Message Dispatch ───────────────────────────────────────────────────────

    async def handle_message(self, message: AgentMessage) -> None:
        if message.type == MessageType.TASK:
            await self._handle_goal(message)
        elif message.type == MessageType.RESULT:
            await self._handle_result(message)
        elif message.type == MessageType.EVENT:
            await self._handle_event(message)
        elif message.type == MessageType.ERROR:
            self._log.error(
                "commander.received_error",
                sender=message.sender,
                error=message.payload.get("error"),
            )

    # ── Goal decomposition ─────────────────────────────────────────────────────

    async def _handle_goal(self, message: AgentMessage) -> None:
        """Decompose a high-level goal and dispatch tasks to agents."""
        raw_goal = message.payload.get("goal", "")
        context = message.payload.get("context", {})
        self._goal_count += 1

        self._log.info("commander.goal_received", goal=raw_goal, goal_num=self._goal_count)
        self.remember("current_goal", raw_goal)

        # ── Build context string for LLM ──────────────────────────────────────
        target_roles = ", ".join(settings.target_roles)
        target_locations = ", ".join(settings.target_locations)
        context_str = (
            f"Target roles: {target_roles}\n"
            f"Target locations: {target_locations}\n"
            f"Min fit score threshold: {settings.min_fit_score}\n"
            f"Additional context: {json.dumps(context)}"
        )

        prompt = (
            f"User goal: {raw_goal}\n\n"
            f"Context:\n{context_str}\n\n"
            "Decompose this goal into tracker and predictor tasks. "
            "Return valid JSON only."
        )

        # ── Ask LLM to decompose ──────────────────────────────────────────────
        llm_response = await self.ask_llm(prompt=prompt, system=COMMANDER_SYSTEM_PROMPT)

        plan = self._parse_plan(llm_response)
        self._log.info(
            "commander.plan_created",
            tracker_tasks=len(plan.get("tracker_tasks", [])),
            predictor_tasks=len(plan.get("predictor_tasks", [])),
        )

        # Store plan in memory
        self.persist("last_plan", plan, tags=["plan"])

        # ── Dispatch tracker tasks ────────────────────────────────────────────
        for task in plan.get("tracker_tasks", []):
            await self.emit(
                topic="jobs",
                msg_type=MessageType.TASK,
                payload=task,
                recipient="tracker",
                priority=MessagePriority.HIGH,
                correlation_id=message.id,
            )

        # ── Dispatch predictor tasks ──────────────────────────────────────────
        for task in plan.get("predictor_tasks", []):
            await self.emit(
                topic="predictions",
                msg_type=MessageType.TASK,
                payload=task,
                recipient="predictor",
                priority=MessagePriority.NORMAL,
                correlation_id=message.id,
            )

        # ── Emit insights as events ───────────────────────────────────────────
        if plan.get("insights"):
            await self.emit_event(
                topic="events",
                payload={"type": "plan_insights", "insights": plan["insights"]},
            )

    def _parse_plan(self, llm_response: str) -> dict[str, Any]:
        """
        Parse LLM JSON response into a plan dict.
        Falls back to a sensible default plan if LLM fails.
        """
        if not llm_response:
            return self._default_plan()

        # Strip markdown code fences if present
        text = llm_response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            plan = json.loads(text)
            if "tracker_tasks" in plan or "predictor_tasks" in plan:
                return plan
        except json.JSONDecodeError:
            self._log.warning("commander.llm_json_parse_failed", response=llm_response[:200])

        return self._default_plan()

    def _default_plan(self) -> dict[str, Any]:
        """Return a sensible default plan when LLM is unavailable."""
        tracker_tasks = [
            {
                "action": "search_jobs",
                "params": {"query": role, "location": loc, "max_results": 20},
            }
            for role in settings.target_roles[:2]
            for loc in settings.target_locations[:2]
        ]
        return {
            "tracker_tasks": tracker_tasks,
            "predictor_tasks": [{"action": "score_all_pending", "params": {}}],
            "insights": ["Running default search plan (LLM not available)"],
        }

    # ── Result aggregation ─────────────────────────────────────────────────────

    async def _handle_result(self, message: AgentMessage) -> None:
        """Aggregate result messages from agents."""
        corr_id = message.correlation_id or "unknown"
        if corr_id not in self._pending_results:
            self._pending_results[corr_id] = []
        self._pending_results[corr_id].append(message.payload)

        self._log.info(
            "commander.result_received",
            sender=message.sender,
            corr_id=corr_id,
            total_results=len(self._pending_results[corr_id]),
        )

    # ── Event handling ─────────────────────────────────────────────────────────

    async def _handle_event(self, message: AgentMessage) -> None:
        """React to system events."""
        event_type = message.payload.get("type", "")

        if event_type == "new_jobs_found":
            count = message.payload.get("count", 0)
            self._log.info("commander.new_jobs_found", count=count)
            # Automatically trigger prediction for new jobs
            await self.emit(
                topic="predictions",
                msg_type=MessageType.TASK,
                payload={"action": "score_all_pending", "params": {}},
                recipient="predictor",
                priority=MessagePriority.NORMAL,
            )

        elif event_type == "weekly_report_ready":
            report_data = message.payload.get("report", {})
            self._latest_report = WeeklyReport(**report_data)
            self._log.info(
                "commander.weekly_report_ready",
                total_jobs=self._latest_report.total_jobs_tracked,
                active_apps=self._latest_report.active_applications,
            )

    # ── Public API ─────────────────────────────────────────────────────────────

    async def run_goal(self, goal: str, context: dict[str, Any] | None = None) -> None:
        """
        Convenience method — directly submit a goal without using the bus.

        Useful for CLI / pipeline entrypoints.
        """
        message = AgentMessage(
            sender="user",
            recipient=self.agent_id,
            topic="commands",
            type=MessageType.TASK,
            priority=MessagePriority.HIGH,
            payload={"goal": goal, "context": context or {}},
        )
        await self._safe_handle(message)

    def get_latest_report(self) -> WeeklyReport | None:
        """Return the most recent weekly report, if available."""
        return self._latest_report

    def status(self) -> dict[str, Any]:
        """Return a snapshot of Commander's current state."""
        return {
            "agent_id": self.agent_id,
            "running": self._running,
            "goals_processed": self._goal_count,
            "current_goal": self.recall("current_goal"),
            "pending_result_groups": len(self._pending_results),
            "has_weekly_report": self._latest_report is not None,
        }
