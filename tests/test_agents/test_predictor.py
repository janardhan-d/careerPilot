"""Tests for the Predictor agent scoring logic."""

from __future__ import annotations

import pytest


class TestPredictorAgent:

    @pytest.mark.asyncio
    async def test_predictor_starts(self, predictor):
        assert predictor._running is True

    @pytest.mark.asyncio
    async def test_compute_score_high_match(self, predictor):
        """High skill overlap should produce a high fit score with APPLY recommendation."""
        predictor._user_skills = ["python", "pytorch", "mlops", "docker", "sql", "fastapi"]
        result = predictor._compute_score(
            job_id="test-1",
            job_title="Machine Learning Engineer",
            company="Google",
            description="python pytorch mlops docker sql",
            skills_mentioned=["python", "pytorch", "mlops", "docker", "sql"],
            is_remote=True,
            easy_apply=True,
        )
        assert result.fit_score >= 65
        assert result.recommendation == "APPLY"
        assert len(result.matched_skills) >= 3

    @pytest.mark.asyncio
    async def test_compute_score_low_match(self, predictor):
        """Low skill overlap should produce SKIP recommendation."""
        predictor._user_skills = ["cooking", "gardening"]
        result = predictor._compute_score(
            job_id="test-2",
            job_title="Staff Engineer",
            company="Unknown Corp",
            description="kubernetes helm terraform aws sre devops",
            skills_mentioned=["kubernetes", "helm", "terraform", "aws"],
            is_remote=False,
            easy_apply=False,
        )
        assert result.recommendation in ("SKIP", "REVIEW")

    @pytest.mark.asyncio
    async def test_response_prob_easy_apply_bonus(self, predictor):
        """Easy apply should boost response_probability."""
        predictor._user_skills = ["python", "sql"]
        result_easy = predictor._compute_score(
            job_id="a", job_title="SWE", company="X",
            description="python sql", skills_mentioned=["python", "sql"],
            is_remote=True, easy_apply=True,
        )
        result_normal = predictor._compute_score(
            job_id="b", job_title="SWE", company="X",
            description="python sql", skills_mentioned=["python", "sql"],
            is_remote=True, easy_apply=False,
        )
        assert result_easy.response_probability >= result_normal.response_probability

    @pytest.mark.asyncio
    async def test_title_match_exact(self, predictor):
        """Exact role match should yield title score of 1.0."""
        from core.config import settings
        # Override settings temporarily
        original = settings.target_roles
        settings.__dict__["target_roles"] = ["Machine Learning Engineer"]
        score = predictor._title_match_score("Machine Learning Engineer")
        settings.__dict__["target_roles"] = original
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_status(self, predictor):
        s = predictor.status()
        assert s["agent_id"] == "predictor"
        assert "user_skills" in s
        assert "scored_jobs" in s
