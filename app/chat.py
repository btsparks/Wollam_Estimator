"""WEIS CLI Chat Interface.

Terminal-based chat interface using Rich for formatted output.
Supports conversation history, slash commands, and sourced answers.
"""

import sys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.ai_engine import QueryEngine
from app import query as db_query

console = Console()


def print_banner():
    """Print the WEIS welcome banner."""
    banner = Text()
    banner.append("WEIS", style="bold cyan")
    banner.append(" - Wollam Estimating Intelligence System\n", style="white")
    banner.append("Ask questions about historical job cost data in plain English.\n", style="dim")
    banner.append("Type ", style="dim")
    banner.append("/help", style="bold yellow")
    banner.append(" for commands, ", style="dim")
    banner.append("/quit", style="bold yellow")
    banner.append(" to exit.", style="dim")

    console.print(Panel(banner, border_style="cyan", padding=(1, 2)))


def print_help():
    """Print available commands."""
    table = Table(title="Commands", show_header=True, header_style="bold cyan",
                  border_style="dim")
    table.add_column("Command", style="bold yellow", width=16)
    table.add_column("Description")

    table.add_row("/help", "Show this help message")
    table.add_row("/status", "Show database status and data summary")
    table.add_row("/disciplines", "List available disciplines")
    table.add_row("/projects", "List cataloged projects")
    table.add_row("/clear", "Clear conversation history (start fresh)")
    table.add_row("/quit or /exit", "Exit WEIS")

    console.print(table)
    console.print("[dim]Or just type a question in plain English.[/dim]\n")


def handle_status():
    """Show database status."""
    overview = db_query.get_database_overview()

    # Projects
    if overview["projects"]:
        table = Table(title="Cataloged Projects", border_style="cyan",
                      show_header=True, header_style="bold")
        table.add_column("Job #", style="bold")
        table.add_column("Name")
        table.add_column("Owner")
        table.add_column("Actual Cost", justify="right")
        table.add_column("Actual MH", justify="right")
        table.add_column("CPI", justify="right")

        for p in overview["projects"]:
            table.add_row(
                p["job_number"],
                p["job_name"],
                p["owner"] or "",
                f"${p['total_actual_cost']:,.0f}" if p.get("total_actual_cost") else "",
                f"{p['total_actual_mh']:,.0f}" if p.get("total_actual_mh") else "",
                f"{p['cpi']:.2f}" if p.get("cpi") else "",
            )
        console.print(table)
    else:
        console.print("[yellow]No projects in database.[/yellow]")

    # Record counts
    console.print()
    table = Table(title="Record Counts", border_style="cyan",
                  show_header=True, header_style="bold")
    table.add_column("Table")
    table.add_column("Records", justify="right")

    total = 0
    for tbl, count in overview["record_counts"].items():
        table.add_row(tbl.replace("_", " ").title(), str(count))
        total += count
    table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")
    console.print(table)


def handle_disciplines():
    """List available disciplines."""
    discs = db_query.get_discipline_summary()
    if not discs:
        console.print("[yellow]No disciplines in database.[/yellow]")
        return

    table = Table(title="Disciplines - Job 8553", border_style="cyan",
                  show_header=True, header_style="bold")
    table.add_column("Code", style="bold")
    table.add_column("Name")
    table.add_column("Budget Cost", justify="right")
    table.add_column("Actual Cost", justify="right")
    table.add_column("Variance %", justify="right")
    table.add_column("Budget MH", justify="right")
    table.add_column("Actual MH", justify="right")

    for d in discs:
        var_pct = f"{d['variance_pct']:.1f}%" if d.get("variance_pct") is not None else ""
        var_style = "green" if d.get("variance_pct", 0) and d["variance_pct"] < 0 else "red"
        table.add_row(
            d["discipline_code"],
            d["discipline_name"],
            f"${d['budget_cost']:,.0f}" if d.get("budget_cost") else "",
            f"${d['actual_cost']:,.0f}" if d.get("actual_cost") else "",
            Text(var_pct, style=var_style) if var_pct else Text(""),
            f"{d['budget_mh']:,.0f}" if d.get("budget_mh") else "",
            f"{d['actual_mh']:,.0f}" if d.get("actual_mh") else "",
        )
    console.print(table)


def handle_projects():
    """List cataloged projects."""
    projects = db_query.get_project_summary()
    if not projects:
        console.print("[yellow]No projects in database.[/yellow]")
        return

    for p in projects:
        console.print(Panel(
            f"[bold]{p['job_name']}[/bold]\n"
            f"Owner: {p.get('owner', 'N/A')}\n"
            f"Location: {p.get('location', 'N/A')}\n"
            f"Type: {p.get('project_type', 'N/A')} | Contract: {p.get('contract_type', 'N/A')}\n"
            f"Duration: {p.get('start_date', '?')} to {p.get('end_date', '?')} "
            f"({p.get('duration_months', '?')} months)\n"
            f"Budget: ${p.get('total_budget_cost', 0):,.0f} | "
            f"Actual: ${p.get('total_actual_cost', 0):,.0f}\n"
            f"Budget MH: {p.get('total_budget_mh', 0):,.0f} | "
            f"Actual MH: {p.get('total_actual_mh', 0):,.0f}\n"
            f"CPI: {p.get('cpi', 'N/A')} | Projected Margin: {p.get('projected_margin', 'N/A')}%",
            title=f"Job {p['job_number']}",
            border_style="cyan",
        ))


def main():
    """Run the WEIS CLI chat interface."""
    print_banner()

    # Initialize query engine
    try:
        engine = QueryEngine()
    except ValueError as e:
        console.print(f"[bold red]Configuration Error:[/bold red] {e}")
        console.print("\n[dim]To set up your API key:[/dim]")
        console.print("  1. Copy .env.example to .env")
        console.print("  2. Add your Anthropic API key to the .env file")
        console.print("  3. Run this again\n")
        console.print("[dim]Slash commands (/status, /disciplines, etc.) work without an API key.[/dim]\n")
        engine = None

    while True:
        try:
            user_input = console.input("[bold green]You:[/bold green] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue

        # Handle slash commands
        cmd = user_input.lower()

        if cmd in ("/quit", "/exit", "/q"):
            console.print("[dim]Goodbye.[/dim]")
            break
        elif cmd == "/help":
            print_help()
            continue
        elif cmd == "/status":
            handle_status()
            continue
        elif cmd == "/disciplines":
            handle_disciplines()
            continue
        elif cmd == "/projects":
            handle_projects()
            continue
        elif cmd == "/clear":
            if engine:
                engine.reset()
            console.print("[dim]Conversation cleared.[/dim]\n")
            continue
        elif cmd.startswith("/"):
            console.print(f"[yellow]Unknown command: {cmd}. Type /help for options.[/yellow]\n")
            continue

        # Query the AI engine
        if engine is None:
            console.print("[red]API key not configured. Only slash commands are available.[/red]")
            console.print("[dim]Set ANTHROPIC_API_KEY in .env to enable AI queries.[/dim]\n")
            continue

        with console.status("[cyan]Querying WEIS database...[/cyan]", spinner="dots"):
            try:
                answer = engine.ask(user_input)
            except Exception as e:
                console.print(f"\n[bold red]Error:[/bold red] {e}\n")
                continue

        console.print()
        console.print(Panel(
            Markdown(answer),
            title="[bold cyan]WEIS[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        ))
        console.print()


if __name__ == "__main__":
    main()
