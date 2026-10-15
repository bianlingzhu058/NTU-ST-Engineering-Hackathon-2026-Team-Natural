# Scenario authoring

- Add one YAML file per scenario under `config/objectives/`.
- Give each scenario a clear name, optional selection weight and parameters, and an ordered skill plan.
- Use registered skills and `{param}` placeholders for parameter values.
- Keep activity bounded, harmless, and suitable for an authorized test VM.
- Review the action log and expected endpoint telemetry when changing a scenario.
