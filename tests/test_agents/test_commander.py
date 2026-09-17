"""
Tests for CommanderAgent.
"""

from __future__ import annotations

import asyncio

import pytest

from models.schemas import AgentMessage, MessageType


class TestCommanderAgent:
    """Test suite for the Commander agent."""

    @pytest.mark.asyncio
    async def test_commander_starts_and_stops(self, commander):
        """Agent should start and stop cleanly."""
        assert commander._running is True
        await commander.stop()
        assert commander._running is False
        # Restart for cleanup
        await commander.start()

    @pytest.mark.asyncio
    async def test_commander_processes_goal(self, commander):
        """Commander should process a goal and increment goal_count."""
        initial = commander._goal_count
        await commander.run_goal("Find 5 ML jobs in Remote")
        # Allow async propagation
        await asyncio.sleep(0.5)
        assert commander._goal_count == initial + 1

    @pytest.mark.asyncio
    async def test_commander_remembers_goal(self, commander):
        """Working memory should hold the latest goal."""
        await commander.run_goal("Apply to 10 AI roles")
        await asyncio.sleep(0.2)
        recalled = commander.recall("current_goal")
        assert recalled == "Apply to 10 AI roles"

    @pytest.mark.asyncio
    async def test_commander_default_plan(self, commander):
        """Default plan should produce tracker and predictor tasks."""
        plan = commander._default_plan()
        assert "tracker_tasks" in plan
        assert "predictor_tasks" in plan
        assert len(plan["tracker_tasks"]) > 0

    @pytest.mark.asyncio
    async def test_commander_parse_valid_plan(self, commander):
        """Commander should correctly parse a valid JSON plan from LLM."""
        valid_json = """
        {
            "tracker_tasks": [
                {"action": "search_jobs", "params": {"query": "ML", "location": "Remote"}}
            ],
            "predictor_tasks": [
                {"action": "score_all_pending", "params": {}}
            ],
            "insights": ["Good market for ML roles"]
        }
        """
        plan = commander._parse_plan(valid_json)
        assert plan["tracker_tasks"][0]["action"] == "search_jobs"
        assert plan["predictor_tasks"][0]["action"] == "score_all_pending"
        assert "Good market" in plan["insights"][0]

    @pytest.mark.asyncio
    async def test_commander_parse_invalid_json_falls_back(self, commander):
        """Commander should fall back to default plan on bad LLM output."""
        plan = commander._parse_plan("This is not valid JSON !!!")
        assert "tracker_tasks" in plan
        assert "predictor_tasks" in plan

    @pytest.mark.asyncio
    async def test_commander_status(self, commander):
        """Status dict should include required keys."""
        s = commander.status()
        assert s["agent_id"] == "commander"
        assert "running" in s
        assert "goals_processed" in s

    @pytest.mark.asyncio
    async def test_commander_result_aggregation(self, commander):
        """Commander should store results keyed by correlation_id."""
        msg = AgentMessage(
            sender="tracker",
            topic="commands",
            type=MessageType.RESULT,
            correlation_id="test-corr-123",
            payload={"action": "search_jobs", "new_jobs": 5},
        )
        await commander._handle_result(msg)
        assert "test-corr-123" in commander._pending_results
        assert commander._pending_results["test-corr-123"][0]["new_jobs"] == 5

    @pytest.mark.asyncio
    async def test_commander_handles_new_jobs_event(self, commander, bus):
        """Commander should react to new_jobs_found by emitting a prediction task."""
        messages_on_predictions = []

        async def capture(m: AgentMessage) -> None:
            messages_on_predictions.append(m)

        bus.subscribe("predictions", capture, "test-capture")

        event = AgentMessage(
            sender="tracker",
            topic="events",
            type=MessageType.EVENT,
            payload={"type": "new_jobs_found", "count": 3, "job_ids": ["a", "b", "c"]},
        )
        await commander._handle_event(event)
        await asyncio.sleep(0.3)

        # Commander should have emitted a score_all_pending task to predictions
        assert any(
            m.payload.get("action") == "score_all_pending"
            for m in messages_on_predictions
        )
