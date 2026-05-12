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
PYTHONPATH=../sim-cli/src:src python -m pytest tests -q
SIM_BLENDER_RUN_INTEGRATION=1 PYTHONPATH=../sim-cli/src:src python -m pytest tests/test_real_blender_live.py -q
```

## License

This package is GPL-3.0-or-later. The Blender-side bridge imports `bpy` when it
runs inside Blender, so the public package uses a GPL-compatible license.
