"""
Tests for job_board_tool and resume_tool.
"""

from __future__ import annotations

import pytest


class TestJobBoardTool:
    """Tests for job_board_tool scrapers and mock fallback."""

    @pytest.mark.asyncio
    async def test_search_jobs_returns_list(self):
        """search_jobs should always return a list (mock fallback guaranteed)."""
        from tools.job_board_tool import search_jobs

        result = await search_jobs(
            query="Machine Learning Engineer",
            location="Remote",
            max_results=5,
        )
        assert isinstance(result, list)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_search_jobs_structure(self):
        """Each job dict must contain required fields."""
        from tools.job_board_tool import search_jobs

        results = await search_jobs(query="Data Scientist", location="Remote", max_results=3)
        for job in results:
            assert "id" in job
            assert "title" in job
            assert "company" in job
            assert "location" in job
            assert "source" in job

    @pytest.mark.asyncio
    async def test_mock_jobs_count(self):
        """Mock job generator should respect n parameter."""
        from tools.job_board_tool import _mock_jobs

        mocks = _mock_jobs("AI Engineer", "Remote", n=7)
        assert len(mocks) == 7

    @pytest.mark.asyncio
    async def test_mock_jobs_remote_flag(self):
        """Mock jobs with 'Remote' location should have is_remote=True."""
        from tools.job_board_tool import _mock_jobs

        mocks = _mock_jobs("AI Engineer", "Remote", n=3)
        assert all(j.is_remote for j in mocks)

    @pytest.mark.asyncio
    async def test_get_job_detail_error_handled(self):
        """get_job_detail should return error dict, not raise, on bad URL."""
        from tools.job_board_tool import get_job_detail

        result = await get_job_detail(url="https://invalid.example.com/job/99999")
        assert "url" in result
        assert result["status"] in ("ok", "error")


class TestResumeTool:
    """Tests for ATS scoring and skill extraction."""

    def test_extract_skills_finds_python(self):
        """Skill extractor should find 'python' in resume text."""
        from tools.resume_tool import extract_skills

        text = "Experienced Python developer with PyTorch and FastAPI skills."
        skills = extract_skills(text)
        assert "python" in skills
        assert "pytorch" in skills
        assert "fastapi" in skills

    def test_extract_skills_case_insensitive(self):
        """Skill extraction should be case-insensitive."""
        from tools.resume_tool import extract_skills

        text = "PYTHON, PYTORCH, SQL, DOCKER"
        skills = extract_skills(text)
        assert "python" in skills
        assert "sql" in skills

    def test_compute_ats_score_perfect_match(self):
        """Perfect skill overlap should yield a high fit_score."""
        from tools.resume_tool import compute_ats_score

        resume = "python pytorch fastapi mlops docker sql langchain"
        jd = "python pytorch fastapi mlops docker sql"
        result = compute_ats_score(resume, jd)
        assert result["fit_score"] >= 70
        assert len(result["matched_skills"]) >= 4

    def test_compute_ats_score_no_match(self):
        """Zero overlap should yield a low fit_score."""
        from tools.resume_tool import compute_ats_score

        resume = "cooking gardening carpentry woodwork"
        jd = "python pytorch sql docker mlops"
        result = compute_ats_score(resume, jd)
        assert result["fit_score"] < 30

    def test_compute_ats_score_fields(self):
        """ATS result dict must contain all required fields."""
        from tools.resume_tool import compute_ats_score

        result = compute_ats_score("python sql docker", "python sql")
        required = {"fit_score", "matched_skills", "missing_skills", "keyword_overlap"}
        assert required.issubset(result.keys())

    def test_compute_ats_score_range(self):
        """Fit score must always be in [0, 100]."""
        from tools.resume_tool import compute_ats_score

        result = compute_ats_score("a b c", "x y z")
        assert 0.0 <= result["fit_score"] <= 100.0

    @pytest.mark.asyncio
    async def test_analyze_resume_missing_file(self):
        """analyze_resume should return error dict for a non-existent file."""
        from tools.resume_tool import analyze_resume

        result = await analyze_resume(
            resume_path="/nonexistent/path/resume.pdf",
            job_description="python machine learning",
        )
        assert "error" in result or result["fit_score"] == 0.0
