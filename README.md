# Claude Code Skills

Custom skills for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that extend its capabilities for marketing technology, analytics, and growth.

## Available Skills

| Skill | Description |
|-------|-------------|
| [martech-audit](./martech-audit/) | Audit a website's marketing technology stack -- GA4, GTM, pixels, data layer, consent, and schema markup -- by inspecting live runtime behavior in a real browser |

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed and configured
- [Superpowers](https://github.com/nicholasgriffintn/claude-code-superpowers) plugin (recommended but not required)

### martech-audit specific requirements

- **chrome-devtools-mcp** -- Required for runtime browser inspection. Install via:
  ```bash
  npx @anthropic-ai/claude-code mcp add chrome-devtools -- npx @anthropic-ai/chrome-devtools-mcp@latest
  ```
- **Tavily MCP** -- Used for site crawling and content extraction. Install via:
  ```bash
  npx @anthropic-ai/claude-code mcp add tavily -- npx -y tavily-mcp@latest
  ```
  Requires a `TAVILY_API_KEY` environment variable ([get one here](https://tavily.com)).
- **Python 3.8+** -- For the deterministic checker script (`check_findings.py`)

## Installation

1. Clone this repo into your Claude Code skills directory:
   ```bash
   # Create the skills directory if it doesn't exist
   mkdir -p ~/.claude/skills

   # Clone
   git clone https://github.com/jasonbhart/skills.git ~/.claude/skills/jasonbhart-skills
   ```

2. Symlink individual skills you want to use:
   ```bash
   ln -s ~/.claude/skills/jasonbhart-skills/martech-audit ~/.claude/skills/martech-audit
   ```

   Or copy them directly:
   ```bash
   cp -r ~/.claude/skills/jasonbhart-skills/martech-audit ~/.claude/skills/martech-audit
   ```

3. Verify the skill is detected by starting Claude Code -- it should appear in the skills list.

## Usage

### martech-audit

Tell Claude Code to audit a website:
```
audit the martech stack on example.com
```

Or use the skill directly:
```
/martech-audit example.com
```

The skill will:
1. Map the site structure via Tavily
2. Open pages in a real browser via chrome-devtools-mcp
3. Run a comprehensive JS eval to detect GTM, GA4, pixels, consent, schema, etc.
4. Run 30 deterministic checks via `check_findings.py`
5. Produce a scored report with findings, recommendations, and next steps

### Standalone deterministic checker

You can run the deterministic checker independently on saved eval JSON:
```bash
python martech-audit/scripts/check_findings.py --dir /path/to/eval-jsons/ --pretty
```

## Skill Structure

Each skill follows this convention:
```
skill-name/
  SKILL.md          # Main skill instructions (loaded by Claude Code)
  scripts/          # Supporting scripts
  references/       # Reference data (lookup tables, rubrics)
  evals/            # Eval definitions for testing
```

## License

MIT
