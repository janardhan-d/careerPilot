"""
CareerPilot — CLI
==================
Rich Typer CLI with four commands:

  careerpilot start           — launch all agents (interactive REPL)
  careerpilot status          — rich table of tracked jobs & applications
  careerpilot report          — AI-generated weekly predictions
  careerpilot apply           — single-job apply flow
  careerpilot config          — show current configuration

Usage
-----
  pip install -e .
  careerpilot --help
  careerpilot start --demo
  careerpilot status
  careerpilot report
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

app = typer.Typer(
    name="careerpilot",
    help="🚀 CareerPilot — AI-powered multi-agent job application manager",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()

BANNER = """
[bold cyan]
   ██████╗ █████╗ ██████╗ ███████╗███████╗██████╗    
  ██╔════╝██╔══██╗██╔══██╗██╔════╝██╔════╝██╔══██╗   
  ██║     ███████║██████╔╝█████╗  █████╗  ██████╔╝   
  ██║     ██╔══██║██╔══██╗██╔══╝  ██╔══╝  ██╔══██╗   
  ╚██████╗██║  ██║██║  ██║███████╗███████╗██║  ██║   
   ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝   
                                                       
         [white]PILOT[/white] ✦ Multi-Agent Job Application AI[/bold cyan]
"""


def _print_banner() -> None:
    console.print(BANNER)


# ── start ─────────────────────────────────────────────────────────────────────

@app.command()
def start(
    goal: Optional[str] = typer.Option(
        None, "--goal", "-g", help="Submit a single goal and exit"
    ),
    demo: bool = typer.Option(
        False, "--demo", help="Run a full end-to-end demonstration"
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", help="Log level: DEBUG|INFO|WARNING|ERROR"
    ),
) -> None:
    """
    🚀 [bold green]Start all CareerPilot agents[/bold green].

    Boots the Commander, Tracker, and Predictor agents and the message bus.
    Without --goal, drops into an interactive REPL.
    """
    _print_banner()

    import os
    os.environ["LOG_LEVEL"] = log_level

    from orchestration.pipeline import _main
    asyncio.run(_main(goal=goal, demo=demo))


# ── status ────────────────────────────────────────────────────────────────────

@app.command()
def status() -> None:
    """
    📊 [bold yellow]Show tracked jobs and active applications[/bold yellow].

    Reads the local SQLite database and renders a rich summary table.
    """
    _print_banner()

    async def _show() -> None:
        import tools  # noqa: F401  — auto-register tools
        from models.database import get_session, init_db
        from models.database import ApplicationORM, JobPostingORM
        from sqlalchemy import func, select

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Loading database...", total=None)
            await init_db()

        async with get_session() as session:
            # ── Jobs table ────────────────────────────────────────────────────
            j_result = await session.execute(
                select(JobPostingORM).order_by(JobPostingORM.discovered_at.desc()).limit(20)
            )
            jobs = j_result.scalars().all()

            jobs_table = Table(
                title="📋 Recent Job Discoveries (last 20)",
                box=box.ROUNDED,
                show_lines=True,
                header_style="bold magenta",
            )
            jobs_table.add_column("#", style="dim", width=3)
            jobs_table.add_column("Title", style="cyan", min_width=25)
            jobs_table.add_column("Company", style="green", min_width=15)
            jobs_table.add_column("Location", min_width=12)
            jobs_table.add_column("Remote", justify="center")
            jobs_table.add_column("Source", style="dim")
            jobs_table.add_column("Discovered", style="dim")

            for i, job in enumerate(jobs, 1):
                discovered = (
                    job.discovered_at.strftime("%b %d %H:%M")
                    if isinstance(job.discovered_at, datetime)
                    else str(job.discovered_at)[:16]
                )
                jobs_table.add_row(
                    str(i),
                    job.title,
                    job.company,
                    job.location[:18],
                    "✅" if job.is_remote else "—",
                    job.source,
                    discovered,
                )

            # ── Applications table ────────────────────────────────────────────
            a_result = await session.execute(
                select(ApplicationORM).order_by(ApplicationORM.last_updated.desc())
            )
            apps = a_result.scalars().all()

            apps_table = Table(
                title="🗂  Applications Pipeline",
                box=box.ROUNDED,
                show_lines=True,
                header_style="bold blue",
            )
            apps_table.add_column("#", style="dim", width=3)
            apps_table.add_column("Role", style="cyan", min_width=22)
            apps_table.add_column("Company", style="green", min_width=14)
            apps_table.add_column("Status", min_width=14)
            apps_table.add_column("Fit", justify="right")
            apps_table.add_column("Updated", style="dim")

            status_colors = {
                "APPLIED": "yellow",
                "INTERVIEWING": "bright_blue",
                "OFFER": "bright_green",
                "ACCEPTED": "green",
                "REJECTED": "red",
                "DISCOVERED": "dim",
                "WITHDRAWN": "dim red",
            }

            for i, app_row in enumerate(apps, 1):
                color = status_colors.get(app_row.status, "white")
                fit = f"{app_row.fit_score:.0f}" if app_row.fit_score else "—"
                updated = (
                    app_row.last_updated.strftime("%b %d")
                    if isinstance(app_row.last_updated, datetime)
                    else "—"
                )
                apps_table.add_row(
                    str(i),
                    app_row.job_title,
                    app_row.company,
                    Text(app_row.status, style=color),
                    fit,
                    updated,
                )

            # ── Stats panel ───────────────────────────────────────────────────
            total_jobs = len(jobs)
            total_apps = len(apps)
            active = sum(
                1 for a in apps if a.status not in {"REJECTED", "WITHDRAWN", "ACCEPTED"}
            )

            summary = (
                f"[bold]Jobs Discovered:[/bold] {total_jobs}   "
                f"[bold]Total Applications:[/bold] {total_apps}   "
                f"[bold]Active:[/bold] {active}"
            )

        console.print(Panel(summary, title="📈 Summary", border_style="cyan"))
        console.print(jobs_table)
        console.print()
        if apps:
            console.print(apps_table)
        else:
            console.print("[dim]No applications tracked yet. Run 'careerpilot apply' to start.[/dim]")

    asyncio.run(_show())


# ── report ────────────────────────────────────────────────────────────────────

@app.command()
def report() -> None:
    """
    🔮 [bold magenta]Generate your weekly AI predictions & recommendations[/bold magenta].

    Reads the prediction database and renders a ranked recommendation report.
    """
    _print_banner()

    async def _show() -> None:
        import tools  # noqa: F401
        from models.database import get_session, init_db, get_top_predictions

        await init_db()
        async with get_session() as session:
            top = await get_top_predictions(session, limit=10)

        if not top:
            console.print(
                Panel(
                    "[yellow]No predictions yet. Run [bold]careerpilot start --demo[/bold] to generate some.[/yellow]",
                    title="🔮 Weekly Report",
                    border_style="yellow",
                )
            )
            return

        # ── Recommendations table ──────────────────────────────────────────────
        rec_table = Table(
            title="🏆 Top Job Recommendations",
            box=box.ROUNDED,
            show_lines=True,
            header_style="bold magenta",
        )
        rec_table.add_column("#", style="dim", width=3)
        rec_table.add_column("Job Title", style="cyan", min_width=24)
        rec_table.add_column("Company", style="green", min_width=14)
        rec_table.add_column("Fit", justify="right", min_width=6)
        rec_table.add_column("Response %", justify="right")
        rec_table.add_column("Action", min_width=8)
        rec_table.add_column("Matched Skills", style="dim", min_width=20)

        action_colors = {"APPLY": "bright_green", "REVIEW": "yellow", "SKIP": "red"}

        for i, pred in enumerate(top, 1):
            fit_color = (
                "bright_green" if pred.fit_score >= 70
                else "yellow" if pred.fit_score >= 50
                else "red"
            )
            action_color = action_colors.get(pred.recommendation, "white")
            matched = ", ".join((pred.matched_skills or [])[:4]) or "—"

            rec_table.add_row(
                str(i),
                pred.job_title,
                pred.company,
                Text(f"{pred.fit_score:.0f}/100", style=fit_color),
                f"{pred.response_probability:.0%}",
                Text(pred.recommendation, style=action_color),
                matched,
            )

        console.print(rec_table)
        console.print()

        # ── Insights ──────────────────────────────────────────────────────────
        apply_count = sum(1 for p in top if p.recommendation == "APPLY")
        avg_fit = sum(p.fit_score for p in top) / len(top)
        console.print(
            Panel(
                f"[bold]Jobs to Apply To:[/bold] {apply_count}  "
                f"[bold]Avg Fit Score:[/bold] {avg_fit:.1f}/100\n\n"
                "[dim]Run [bold white]careerpilot start[/bold white] and say "
                "'Generate my weekly report' for full AI-powered insights.[/dim]",
                title="💡 Insights",
                border_style="green",
            )
        )

    asyncio.run(_show())


# ── apply ─────────────────────────────────────────────────────────────────────

@app.command()
def apply(
    job_url: Optional[str] = typer.Option(
        None, "--job-url", "-u", help="LinkedIn or Indeed job URL"
    ),
    job_title: Optional[str] = typer.Option(None, "--title", "-t", help="Job title"),
    company: Optional[str] = typer.Option(None, "--company", "-c", help="Company name"),
    resume: Optional[str] = typer.Option(
        None, "--resume", "-r", help="Path to your resume (PDF/DOCX)"
    ),
) -> None:
    """
    📝 [bold blue]Track and score a specific job application[/bold blue].

    Provide a job URL to fetch details, or manually supply title + company.
    """
    _print_banner()

    if not job_url and not (job_title and company):
        console.print(
            "[red]Provide either --job-url or both --title and --company.[/red]"
        )
        raise typer.Exit(1)

    async def _apply() -> None:
        import tools  # noqa: F401
        from orchestration.pipeline import CareerPilotPipeline
        from models.schemas import JobPosting, JobSource

        pipeline = CareerPilotPipeline()
        await pipeline.start()

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:

                # Fetch job details if URL provided
                description = ""
                if job_url:
                    progress.add_task("Fetching job details...", total=None)
                    detail = await pipeline.commander.use_tool("get_job_detail", url=job_url)
                    description = detail.get("description", "")

                # Build a JobPosting
                job = JobPosting(
                    title=job_title or "Unknown",
                    company=company or "Unknown",
                    location="Unknown",
                    description=description,
                    source_url=job_url or "",
                    source=JobSource.MANUAL,
                )

                # Score it
                progress.add_task("Scoring job fit...", total=None)
                if resume and description:
                    score_result = await pipeline.commander.use_tool(
                        "analyze_resume",
                        resume_path=resume,
                        job_description=description,
                    )
                    job_fit = score_result.get("fit_score", 0.0)
                    matched = score_result.get("matched_skills", [])
                    missing = score_result.get("missing_skills", [])
                else:
                    job_fit = None
                    matched = []
                    missing = []

                # Track the application
                progress.add_task("Tracking application...", total=None)
                app = await pipeline.tracker.create_application(job)

        finally:
            await pipeline.stop()

        # ── Output ─────────────────────────────────────────────────────────────
        console.print(
            Panel(
                f"[bold]Role:[/bold]    {job.title}\n"
                f"[bold]Company:[/bold] {job.company}\n"
                f"[bold]Status:[/bold]  [yellow]APPLIED[/yellow]\n"
                f"[bold]App ID:[/bold]  [dim]{app.id}[/dim]"
                + (
                    f"\n\n[bold]Fit Score:[/bold]      [{'bright_green' if (job_fit or 0) >= 65 else 'yellow'}]{job_fit:.0f}/100[/]\n"
                    f"[bold]Matched Skills:[/bold] {', '.join(matched[:5]) or 'N/A'}\n"
                    f"[bold]Missing Skills:[/bold] {', '.join(missing[:5]) or 'None'}"
                    if job_fit is not None
                    else ""
                ),
                title="✅ Application Tracked",
                border_style="green",
            )
        )

    asyncio.run(_apply())


# ── config ────────────────────────────────────────────────────────────────────

@app.command()
def config() -> None:
    """
    ⚙️  [bold]Show current CareerPilot configuration[/bold].
    """
    from core.config import settings

    cfg_table = Table(title="⚙️  Configuration", box=box.SIMPLE, header_style="bold")
    cfg_table.add_column("Setting", style="cyan", min_width=28)
    cfg_table.add_column("Value", style="white")

    rows = [
        ("LLM Backend", "Ollama" if settings.use_ollama else "OpenAI"),
        ("OpenAI Model", settings.openai_model if not settings.use_ollama else "—"),
        ("Ollama Model", settings.ollama_model if settings.use_ollama else "—"),
        ("Database URL", settings.database_url),
        ("Target Roles", ", ".join(settings.target_roles)),
        ("Target Locations", ", ".join(settings.target_locations)),
        ("Min Fit Score", str(settings.min_fit_score)),
        ("Max Daily Apps", str(settings.max_daily_applications)),
        ("Poll Interval", f"{settings.tracker_poll_interval}s"),
        ("LinkedIn Email", settings.linkedin_email or "[dim]not set[/dim]"),
        ("Gmail Creds", "✅ found" if __import__("os").path.exists(settings.gmail_credentials_path) else "❌ not found"),
        ("Log Level", settings.log_level),
    ]

    for key, val in rows:
        cfg_table.add_row(key, val)

    console.print(cfg_table)


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
