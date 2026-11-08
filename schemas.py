"""Model-facing tool schemas. There is deliberately no tool that records a human review."""

_PROJECT = {
    "type": "string",
    "maxLength": 1024,
    "description": "Absolute path of the project folder that contains syw.toml.",
}

TOOL_SCHEMAS = {
    "syw_board": {
        "name": "syw_board",
        "description": (
            "Show Your Work board for a project: every acceptance criterion with four SEPARATE "
            "statuses: coverage (is any test linked?), outcome (latest imported run), freshness "
            "(has tracked code changed since that run?) and human review. Read-only. Use it before "
            "claiming work is done; report untested, failing, stale and unreviewed requirements "
            "honestly. You cannot mark anything reviewed or accepted. Only the human can."
        ),
        "parameters": {
            "type": "object",
            "properties": {"project": _PROJECT},
            "required": ["project"],
            "additionalProperties": False,
        },
    },
    "syw_link": {
        "name": "syw_link",
        "description": (
            "Link one or more test ids to an acceptance criterion (recorded as linked by the "
            "agent). Test ids match the JUnit report: 'classname::name' (for pytest, e.g. "
            "'tests.test_tip::test_split'). Linking is a coverage CLAIM the human can inspect, not proof."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project": _PROJECT,
                "requirement": {"type": "string", "maxLength": 32},
                "test_ids": {"type": "array", "items": {"type": "string", "maxLength": 500},
                             "minItems": 1, "maxItems": 50},
            },
            "required": ["project", "requirement", "test_ids"],
            "additionalProperties": False,
        },
    },
    "syw_import": {
        "name": "syw_import",
        "description": (
            "Import a JUnit XML test report (max 5 MB), or a folder of them such as Maven target/surefire-reports, from inside the project folder as ONE new, "
            "append-only run. Records the report hash and a fingerprint of the tracked files. Run "
            "the tests yourself first (e.g. `pytest --junitxml=report.xml`). This tool runs nothing. "
            "Note: a harness exit code of 0 does not mean the tests passed; import and read the board."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project": _PROJECT,
                "report_path": {"type": "string", "maxLength": 1024,
                                "description": "File or folder path relative to the project folder."},
            },
            "required": ["project", "report_path"],
            "additionalProperties": False,
        },
    },
    "syw_run_detail": {
        "name": "syw_run_detail",
        "description": "Per-test outcomes and failure messages for one imported run (or the latest).",
        "parameters": {
            "type": "object",
            "properties": {
                "project": _PROJECT,
                "run_id": {"type": "string", "maxLength": 32,
                           "description": "Omit for the latest run."},
            },
            "required": ["project"],
            "additionalProperties": False,
        },
    },
}
