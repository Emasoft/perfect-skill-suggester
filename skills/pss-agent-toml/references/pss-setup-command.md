# Using the /pss-setup-agent Command

The simplest way to invoke this entire workflow:

```
/pss-setup-agent /path/to/agent.md
/pss-setup-agent /path/to/agent.md --requirements /path/to/prd.md /path/to/tech-spec.md
/pss-setup-agent plugin-name:agent-name
/pss-setup-agent /path/to/agent.md --output /custom/output.agent.toml
```

This command spawns the `pss-agent-profiler` agent, which follows the full Phase 1-6 workflow with AI reasoning at every step.
