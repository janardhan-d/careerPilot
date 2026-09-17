"""
Tests for TrackerAgent — job discovery, deduplication, and application creation.
"""

from __future__ import annotations

import asyncio

import pytest

from models.schemas import AgentMessage, JobPosting, JobSource, MessageType


class TestTrackerAgent:
    """Unit tests for the Tracker agent."""

    @pytest.mark.asyncio
    async def test_tracker_starts(self, tracker):
        assert tracker._running is True

    @pytest.mark.asyncio
    async def test_deduplication_prevents_duplicates(self, tracker, sample_job):
        """Second insertion of same title+company must be ignored."""
        first_batch = await tracker._deduplicate_and_persist([sample_job])
        assert len(first_batch) == 1

        second_batch = await tracker._deduplicate_and_persist([sample_job])
        assert len(second_batch) == 0  # already known

    @pytest.mark.asyncio
    async def test_deduplication_allows_new_jobs(self, tracker, sample_jobs):
        """Two different jobs should both be persisted."""
        new = await tracker._deduplicate_and_persist(sample_jobs)
        assert len(new) == 2

    @pytest.mark.asyncio
    async def test_job_key_normalisation(self, tracker):
        """Job key must be lowercase to catch case-variant duplicates."""
        from models.schemas import JobPosting, JobSource
        job = JobPosting(
            title="Machine Learning ENGINEER",
            company="ACME CORP",
            location="Remote",
            source=JobSource.LINKEDIN,
        )
        key = tracker._job_key(job)
        assert key == "machine learning engineer|acme corp"

    @pytest.mark.asyncio
    async def test_create_application(self, tracker, sample_job):
        """create_application should persist an APPLIED record in the DB."""
        await tracker._deduplicate_and_persist([sample_job])
        app = await tracker.create_application(sample_job)
        assert app.status.value == "APPLIED"
        assert app.job_id == sample_job.id
        assert app.company == sample_job.company

    @pytest.mark.asyncio
    async def test_search_task_emits_event(self, tracker, bus):
        """After a search task, an event should be published on 'events' topic."""
        events_received = []

        async def capture(msg: AgentMessage) -> None:
            events_received.append(msg)

        bus.subscribe("events", capture, "test-events-listener")

        task_msg = AgentMessage(
            sender="commander",
            topic="jobs",
            type=MessageType.TASK,
            payload={
                "action": "search_jobs",
                "params": {"query": "ML Engineer", "location": "Remote", "max_results": 5},
            },
        )
        await tracker.handle_message(task_msg)
        await asyncio.sleep(0.5)

        # At least one new_jobs_found event should be emitted
        types = [m.payload.get("type") for m in events_received]
        assert "new_jobs_found" in types

    @pytest.mark.asyncio
    async def test_status_keys(self, tracker):
        """Tracker status must include required keys."""
        s = tracker.status()
        assert s["agent_id"] == "tracker"
        assert "known_jobs" in s
        assert "poll_interval_secs" in s

    @pytest.mark.asyncio
    async def test_unknown_action_does_not_raise(self, tracker):
        """Unknown action in a TASK message must be silently ignored."""
        msg = AgentMessage(
            sender="commander",
            topic="jobs",
            type=MessageType.TASK,
            payload={"action": "nonexistent_action", "params": {}},
        )
        # Should not raise
        await tracker.handle_message(msg)
