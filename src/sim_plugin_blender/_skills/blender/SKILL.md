---
name: blender-sim
description: Use when working with Blender through sim: live visible editing, bounded bpy snippets, scene inspection, checkpoints, renders, and optional composition with Blender MCP tools.
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

## Optional MCP composition

Third-party tools such as `blender-mcp` and `blend-ai` can be useful for richer
tool surfaces. Do not silently install or start them. If the user already uses
one, keep `sim` responsible for connection health, checkpoints, and structured
inspection.

## Guardrails

- Use short `bpy` snippets and inspect after each meaningful edit.
- Save `.blend` checkpoints for non-trivial work.
- Prefer numeric/structured checks where possible; visual polish still needs
  human review.
- Do not assume a GUI selection survived a human edit; inspect it.
