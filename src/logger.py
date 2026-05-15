from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme
import json

# Define custom theme for different agents
agent_theme = Theme({
    "sensor": "cyan",
    "auditor": "magenta",
    "ticketer": "yellow",
    "remediator": "red",
    "validator": "green",
    "narrator": "blue",
    "system": "bold white"
})

console = Console(theme=agent_theme)

def log_agent_action(agent_name: str, title: str, content: str):
    """
    Prints a beautiful panel for an agent's action.
    """
    color = agent_name.lower()
    # Default to system if color not in theme
    if color not in agent_theme.styles:
        color = "system"
        
    panel = Panel(
        content,
        title=f"[bold]{title}[/bold]",
        subtitle=f"[dim]Agent: {agent_name}[/dim]",
        border_style=color,
        padding=(1, 2)
    )
    console.print(panel)
    console.print() # Add spacing

def print_system_msg(msg: str):
    console.print(f"[system]{msg}[/system]")
