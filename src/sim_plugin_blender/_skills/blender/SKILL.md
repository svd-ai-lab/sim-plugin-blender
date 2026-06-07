---
name: blender-sim
description: Use when working with Blender through sim: live visible editing, bounded bpy snippets, scene inspection, checkpoints, renders, and optional explicit composition with Blender Lab MCP tools.
---

# blender-sim

Use `sim-plugin-blender` when the task needs a reliable live Blender editing
loop that an engineer can inspect and interrupt.

## Default live loop

Start with a visible Blender session when the user wants collaboration:

```bash
uv run sim check blender
uv run sim connect --solver blender --ui-mode gui
uv run sim inspect blender.scene.summary
```

Then work in bounded steps:

```bash
uv run sim exec --file step.py --label geometry
uv run sim inspect last.result
uv run sim inspect blender.scene.summary
```

After a human edits the open Blender scene, inspect again before continuing.
Treat the live scene as source of truth, not your previous code.

## Shell-composable diagnostics

The bridge is launched by Blender's own CLI:

```bash
blender model.blend \
  --python sim_blender_bridge.py \
  -- --sim-host 127.0.0.1 --sim-port 9876 --session-id manual
```

Logs live under `.sim/blender/`. Use ordinary shell tools (`tail`, `grep`,
`jq`, small Python socket probes) before guessing.

## One-shot path

Use one-shot background scripts for deterministic smoke and batch jobs:

```bash
uv run sim run --solver blender path/to/script.py
```

Scripts should print a final JSON object line and save explicit artifacts such
as `.blend`, `.json`, renders, or exported meshes.

## Cookbook pattern

Runnable recipes belong in the project-owned recipe/docs repository, not this
plugin repo. For demonstrator geometry, keep the script self-contained and
runnable through both the live bridge and one-shot path. Set `_result` for
`sim exec`, print the same JSON for `sim run`, save a `.blend` checkpoint, and
include dimensions or source assumptions in the result payload.

## Optional Blender Lab MCP companion

The official Blender Lab MCP Server can be useful when the user already has an
MCP-capable agent and wants richer Blender API/manual resources or
natural-language scene exploration. It is an optional companion, not the
default sim transport.

Do not silently install, enable, or start MCP tooling. Do not claim MCP tools
exist unless the user has installed the Blender Lab add-on, started/configured
the `blender-mcp` server in their MCP client, and understands the security
tradeoff: Blender Lab warns that the MCP server executes LLM-generated code in
Blender without guards. Prefer an isolated VM or a machine without sensitive
data.

If the user chooses MCP composition:

```bash
python -m pip install "git+https://projects.blender.org/lab/blender_mcp.git#subdirectory=mcp"
```

Then have them install and enable the add-on from `https://lab.blender.org/` or
the Blender Lab MCP page, configure their MCP client to run `blender-mcp`, and
keep `sim` responsible for connection health, checkpoints, screenshots, and
structured inspection. After any MCP-driven scene mutation, inspect before
continuing:

```bash
uv run sim inspect blender.scene.summary
uv run sim screenshot --output scene-after-mcp.png
```

## Guardrails

- Use short `bpy` snippets and inspect after each meaningful edit.
- Save `.blend` checkpoints for non-trivial work.
- Prefer numeric/structured checks where possible; visual polish still needs
  human review.
- Do not assume a GUI selection survived a human edit; inspect it.
