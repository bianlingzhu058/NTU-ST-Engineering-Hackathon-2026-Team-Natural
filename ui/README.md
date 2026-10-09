# Operator interface

- Intended to contain a small local interface for choosing a scenario and duration.
- The interface should call the existing `agent` runtime rather than reimplementing execution.
- Show run ID, scenario, status, and errors; provide clear start and stop controls.
- Keep desktop execution explicit and label runs as synthetic and auditable.
- No UI framework or executable interface is implemented yet.
