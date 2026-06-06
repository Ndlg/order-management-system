# Codex Instructions

Before changing code, read these files:

1. docs/project_rules.md
2. docs/requirements/v7.9.3-collector-agent.md

For v7.9.3, the source of truth is:

docs/requirements/v7.9.3-collector-agent.md

Required rules:

- Remove scripts/collector_client_legacy/.
- Create OrderCollectorAgent under src/plugins/collector_agent/.
- The client-side agent must only read local printer component data and upload raw waybill records.
- Do not implement collection modes.
- Do not implement client-side recognition.
- Do not filter, merge, or discard printer tasks on the client side.
- Never drop any task_id or component_rowid.
- Each rowid entering the batch range must produce at least one upload record.
- Build artifacts must go under versions/vX.Y.Z/.
- Temporary files must go under tmp/.
- Do not create garbage files in the repository root.
- Do not modify docs/requirements/v7.9.3-collector-agent.md unless the user explicitly asks.

Execution flow:

1. Read the requirement file.
2. Output an implementation plan.
3. Change code.
4. Run tests.
5. Update version documents and test report.
6. Check that the repository root is clean.