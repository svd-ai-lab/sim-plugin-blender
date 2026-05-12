# Blender Cookbook

Runnable examples for `sim-plugin-blender`. These scripts are intended for live
sessions first, and also work as one-shot background smoke scripts when Blender
is installed.

## SpaceX Starship Stack

`starship_stack.py` creates an approximate Starship/Super Heavy vehicle using
public proportions from SpaceX: a 123 m integrated stack, 9 m diameter, 71 m
Super Heavy booster, and 52 m Starship upper stage.

Live co-working loop:

```powershell
uv run sim connect --solver blender --ui-mode gui --workspace .sim-e2e/starship
uv run sim exec --file cookbook/starship_stack.py --label starship-stack
uv run sim inspect blender.scene.summary
uv run sim screenshot --output .sim-e2e/starship/starship_stack.png
uv run sim disconnect --stop-server
```

One-shot background run:

```powershell
uv run sim run --solver blender cookbook/starship_stack.py
```

The script saves `starship_stack.blend` in the current working directory unless
`SIM_BLENDER_STARSHIP_BLEND` points to another output file.
