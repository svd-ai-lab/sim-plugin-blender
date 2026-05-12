# sim-plugin-blender

`sim-plugin-blender` lets agents operate Blender through `sim` with a live,
human-visible editing loop:

```bash
uv run sim connect --solver blender --ui-mode gui
uv run sim exec --file step.py
uv run sim inspect blender.scene.summary
uv run sim disconnect
```

The plugin launches Blender with its documented command-line Python bootstrap,
then talks to a small localhost bridge running inside Blender. The same bridge
can also run headless for integration tests, and one-shot `sim run` remains
available for deterministic batch scripts.

Blender itself is not bundled. Install Blender from blender.org, Homebrew, your
OS package manager, or your studio-managed distribution, then expose the binary
on `PATH` or set `SIM_BLENDER_EXE`.

## Install

For agent projects, install sim-cli-core and the Blender plugin in the project
environment:

```bash
uv init  # only if this is not already a uv project
uv add sim-cli-core sim-plugin-blender
uv run sim plugin sync-skills --target .agents/skills --copy
uv run sim check blender
uv run sim plugin doctor blender --deep
```

For Claude Code, sync the bundled skill to `.claude/skills` instead:

```bash
uv run sim plugin sync-skills --target .claude/skills --copy
```

`uv run sim ...` runs sim from this project environment, so it sees this
project's plugins. Without uv, create and activate a venv, then install
`sim-cli-core` plus this plugin with `python -m pip`.

## Shell-composable launch

The live bridge is intentionally plain CLI:

```bash
blender path/to/model.blend \
  --python src/sim_plugin_blender/bridge/sim_blender_bridge.py \
  -- --sim-host 127.0.0.1 --sim-port 9876 --session-id manual
```

That makes failures debuggable with normal tools: `tail` the `.sim` logs, probe
the port with a small JSON client, and run the same command outside an agent.

## Development

Use source checkouts and targeted tests while developing. Build wheels only for
release validation.

```bash
git clone https://github.com/svd-ai-lab/sim-plugin-blender
cd sim-plugin-blender
uv sync --extra test
uv run sim plugin list
uv run sim check blender
uv run --extra test pytest --basetemp .pytest_basetemp/local -q -m "not integration"
uv build
```

Run the real Blender smoke only on a machine with Blender installed:

```bash
SIM_BLENDER_RUN_INTEGRATION=1 uv run --extra test pytest tests/test_real_blender_live.py -q
```

## Cookbook

Runnable examples live in
[`sim-cookbook`](https://github.com/svd-ai-lab/sim-cookbook). The Starship
stack recipe creates an approximate SpaceX Starship/Super Heavy model in a live
Blender session and saves a `.blend` checkpoint:

```bash
uv run sim connect --solver blender --ui-mode gui --workspace .sim-e2e/starship
uv run sim exec --file blender/examples/starship_stack/00_create_starship_stack.py --label starship-stack
uv run sim screenshot --output .sim-e2e/starship/starship_stack.png
```

## License

This package is GPL-3.0-or-later. The Blender-side bridge imports `bpy` when it
runs inside Blender, so the public package uses a GPL-compatible license.
