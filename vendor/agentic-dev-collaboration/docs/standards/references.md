# Standards and References

The framework prefers open, text-based formats with multiple implementations.

## Repository instructions

- [AGENTS.md](https://agents.md/) defines a simple repository instruction file
  intended for coding agents.

## Reusable skills

- [Agent Skills specification](https://agentskills.io/) defines portable
  `SKILL.md` packages.
- [GitHub Agent Skills documentation](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)
  describes Agent Skills as an open standard used by multiple AI systems.

## Tools

- [Model Context Protocol](https://modelcontextprotocol.io/specification/) is an
  open protocol for connecting AI applications to tools and context.

MCP is a tool and context protocol, not a universal software-development
workflow or agent lifecycle-hook format.

## Architecture decisions

- [Markdown Architectural Decision Records](https://adr.github.io/madr/)
  provides the base structure used by this repository's ADR templates.

## Data contracts

- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) validates agent,
  task, finding, verdict, hook, and platform manifests.

## Hooks

Agent runtimes currently expose different lifecycle events and configuration
formats. The canonical hook event schema in this repository is therefore a
portable internal contract, not a claim of broad industry standardization.
Adapters must document their mapping and limitations.
