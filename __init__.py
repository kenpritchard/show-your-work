"""Show Your Work: native Hermes registrations. Importing performs no I/O."""

import json

PING_SCHEMA = {
    "name": "syw_ping",
    "description": "Phase 0 spike: confirm the Show Your Work plugin is loaded.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}


def _ping(args, **kwargs):
    return json.dumps({"ok": True, "plugin": "show-your-work", "phase": 0})


def register(ctx):
    ctx.register_tool(
        name="syw_ping",
        toolset="show_your_work",
        schema=PING_SCHEMA,
        handler=_ping,
        check_fn=lambda: True,
    )
