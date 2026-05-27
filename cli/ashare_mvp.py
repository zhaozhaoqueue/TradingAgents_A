from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown

from tradingagents.ashare_mvp import (
    DailyReviewInput,
    DailyReviewPipeline,
    StockMoveInput,
    StockMovePipeline,
)

console = Console()

app = typer.Typer(
    name="ashare",
    help="A-share MVP workflows",
    add_completion=True,
)


@app.command("stock-move")
def stock_move(
    symbol: str = typer.Option(..., "--symbol", help="A-share ticker such as 600519.SH"),
    date: str = typer.Option(..., "--date", help="Trade date in YYYY-MM-DD"),
    output: Path | None = typer.Option(None, "--output", help="Optional markdown output path"),
    print_report: bool = typer.Option(True, "--print/--no-print", help="Render report to terminal"),
):
    pipeline = StockMovePipeline()
    report = pipeline.run(StockMoveInput(symbol=symbol, trade_date=date))

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.markdown, encoding="utf-8")
        console.print(f"[green]Saved report:[/green] {output}")

    if print_report:
        console.print(Markdown(report.markdown))


@app.command("daily-review")
def daily_review(
    date: str = typer.Option(..., "--date", help="Trade date in YYYY-MM-DD"),
    top_sectors: int = typer.Option(5, "--top-sectors", help="How many hot sectors to render"),
    top_movers: int = typer.Option(10, "--top-movers", help="How many movers to analyze"),
    output: Path | None = typer.Option(None, "--output", help="Optional markdown output path"),
    print_report: bool = typer.Option(True, "--print/--no-print", help="Render report to terminal"),
):
    pipeline = DailyReviewPipeline()
    report = pipeline.run(
        DailyReviewInput(
            trade_date=date,
            top_n_sectors=top_sectors,
            top_n_movers=top_movers,
        )
    )

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.markdown, encoding="utf-8")
        console.print(f"[green]Saved report:[/green] {output}")

    if print_report:
        console.print(Markdown(report.markdown))
