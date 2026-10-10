# Scenario authoring

- Add one YAML file per scenario under `config/objectives/`.
- The UI objective editor saves customized objectives into the same folder as new YAML files and never overwrites its source objective.
- Give each scenario a clear name, optional selection weight and parameters, and an ordered skill plan.
- Use registered skills and `{param}` placeholders for parameter values.
- Keep activity bounded, harmless, and suitable for an authorized test VM.
- Skills report the current scenario and skill to the operator interface. Pause and stop are checked between backend input actions; keep each individual skill action short enough to finish safely.
- Review the action log and expected endpoint telemetry when changing a scenario.
