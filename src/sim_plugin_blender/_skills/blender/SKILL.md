---
name: blender-sim
description: Use for live visible Blender modeling, scene inspection, bounded bpy edits, redraws, checkpoints, screenshots, renders, and validation. Prefer an already-connected official Blender MCP session for direct in-process updates and visible review; use the sim Blender bridge or one-shot execution when MCP is unavailable or isolation is required.
---

# blender-sim

Use an already-connected official Blender MCP session when the user wants to
watch the current Blender file change. Use `sim-plugin-blender` when MCP is not
available, structured bridge inspection is needed, or a repeatable isolated run
is preferable.

## Transport selection

1. If official Blender MCP tools are callable and connected, inspect and edit
   the current Blender process through MCP.
2. Otherwise use the visible `sim-plugin-blender` live bridge.
3. Use one-shot background Blender only for isolated batch or smoke work.

Do not modify a background file and ask the user to reload it when a connected
live transport can update the current scene directly.

## Official Blender MCP live loop

For every meaningful geometry change:

1. inspect the current file, scene, mode, active object, and target collection
2. execute one bounded `bpy` change in the connected Blender process
3. call `view_layer.update()` and tag `VIEW_3D` areas for redraw
4. save a named `.blend` checkpoint
5. capture the Blender window or viewport through MCP and show it to the user
6. run numeric or orthographic validation appropriate to the task

Keep visual screenshots and geometry validation separate. A refreshed viewport
proves that Blender updated; it does not prove dimensions or topology are right.

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

## Blender Lab MCP setup

The official Blender Lab MCP Server is the preferred live transport when it is
already configured and connected.

Do not silently install, enable, or start MCP tooling. Do not claim MCP tools
exist unless the user has installed the Blender Lab add-on, started/configured
the `blender-mcp` server in their MCP client, and understands the security
tradeoff: Blender Lab warns that the MCP server executes LLM-generated code in
Blender without guards. Prefer an isolated VM or a machine without sensitive
data.

If the user explicitly asks to install or configure MCP:

```bash
python -m pip install "git+https://projects.blender.org/lab/blender_mcp.git#subdirectory=mcp"
```

Then have them install and enable the add-on from `https://lab.blender.org/` or
the Blender Lab MCP page and configure their MCP client to run `blender-mcp`.
After any MCP-driven scene mutation, inspect and capture evidence before
continuing. The `sim` bridge may provide additional structured inspection when
both transports intentionally share the same live scene:

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
