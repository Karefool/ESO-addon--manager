import argparse
import sys
from rich.console import Console
from rich.table import Table
from manager import AddonManager

console = Console()

def search_cmd(manager, args):
    results = manager.search_addons(args.query)
    if not results:
        console.print(f"[yellow]No addons found matching '{args.query}'[/yellow]")
        return
        
    table = Table(title=f"Search Results for '{args.query}'")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="green")
    table.add_column("Author", style="magenta")
    table.add_column("Version", justify="right", style="blue")
    
    # limit to 20 results
    for addon in results[:20]:
        table.add_row(
            str(addon.get('UID')),
            addon.get('UIName'),
            addon.get('UIAuthorName'),
            addon.get('UIVersion')
        )
        
    console.print(table)

def install_cmd(manager, args):
    # args.addon can be an ID or a name
    query = args.addon
    
    if query.isdigit():
        addon_id = query
    else:
        results = manager.search_addons(query)
        if not results:
            console.print(f"[red]Could not find addon '{query}'[/red]")
            return
            
        if len(results) > 1 and results[0]['UIName'].lower() != query.lower():
            console.print(f"[yellow]Multiple addons found for '{query}'. Please specify an ID instead.[/yellow]")
            search_cmd(manager, argparse.Namespace(query=query))
            return
            
        addon_id = results[0]['UID']
        
    console.print(f"[cyan]Installing addon ID {addon_id}...[/cyan]")
    # TODO implement manager install logic better wrapper
    manager.install_addon(addon_id)
    console.print(f"[green]Successfully installed addon and dependencies![/green]")

def list_cmd(manager, args):
    addons = manager.get_installed_addons()
    if not addons:
        console.print("[yellow]No addons currently installed in your AddOns directory.[/yellow]")
        return
        
    table = Table(title="Installed Addons (Local Folders)")
    table.add_column("Folder Name", style="green")
    
    for addon in addons:
        table.add_row(addon)
        
    console.print(table)

def main():
    parser = argparse.ArgumentParser(description="ESO Addon Manager CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search for an addon")
    search_parser.add_argument("query", help="Addon name to search for")
    
    # Install command
    install_parser = subparsers.add_parser("install", help="Install an addon by name or ID")
    install_parser.add_argument("addon", help="Addon name or ID to install")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List installed addons")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
        
    try:
        manager = AddonManager()
    except Exception as e:
        console.print(f"[red]Failed to initialize AddonManager: {e}[/red]")
        sys.exit(1)
        
    if args.command == "search":
        search_cmd(manager, args)
    elif args.command == "install":
        install_cmd(manager, args)
    elif args.command == "list":
        list_cmd(manager, args)

if __name__ == "__main__":
    main()
