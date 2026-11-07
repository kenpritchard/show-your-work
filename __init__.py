"""Show Your Work: native Hermes registrations. Importing performs no I/O."""

from pathlib import Path


def register(ctx):
    from .handlers import cli_run, cli_setup, slash, tool
    from .schemas import TOOL_SCHEMAS

    for name, schema in TOOL_SCHEMAS.items():
        ctx.register_tool(
            name=name,
            toolset="show_your_work",
            schema=schema,
            handler=tool(name),
            check_fn=lambda: True,
            emoji="🧾",
        )
    ctx.register_command(
        "syw",
        handler=slash,
        description="Show Your Work: requirement board; accept/reject (human sign-off); export",
        args_hint="[board|accept|reject|export] ...",
    )
    ctx.register_cli_command(
        name="syw",
        help="Show Your Work: acceptance-criteria evidence board",
        setup_fn=cli_setup,
        handler_fn=cli_run,
    )
    ctx.register_skill(
        name="workflow",
        path=Path(__file__).parent / "skills" / "workflow" / "SKILL.md",
        description="Prove work against acceptance criteria with the Show Your Work board.",
    )
