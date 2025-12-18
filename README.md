# Cert Speedrun Optimizer

An MCP server and web interface for certification exam preparation using speedrun training methodologies. Focus your practice on weak areas and track your progress.

## Features

- **Question Bank Management**: Create and manage certification exam question banks via MCP tools
- **Bias-Free Answers**: Built-in validation to prevent answer length bias and weak distractors
- **Speedrun Mode**: Automatically prioritizes questions you struggle with most
- **Performance Stats**: Track accuracy by topic and identify weak areas
- **Session Persistence**: Resume practice sessions even after server restart
- **Web Interface**: Clean, HTMX-powered UI for practicing questions

## Quick Start with Docker

```bash
# Run with persistent data
docker run -d -p 8080:80 -v cert-data:/data ghcr.io/levitrammell/cert-speedrun-optimizer

# Access the web UI at http://localhost:8080
# MCP endpoint at http://localhost:8080/mcp/
```

Or with docker-compose:

```bash
docker compose up -d
```

## Local Development

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
# Install dependencies
uv sync

# Initialize database
uv run python -c "from cert_speedrun.db.database import init_db; import asyncio; asyncio.run(init_db())"

# Run MCP server (for Claude Code)
uv run fastmcp run server.py

# Or run web UI
uv run uvicorn cert_speedrun.web.app:app --port 3000
```

## MCP Tools

### Question Bank Management

| Tool | Description |
|------|-------------|
| `create_exam` | Create a certification exam container |
| `create_topic` | Create a topic within an exam |
| `create_question` | Create a question with answers |
| `list_exams` | List all exams |
| `list_topics` | List topics for an exam |
| `list_questions` | List questions with filtering |
| `search_questions` | Search questions by keyword |

### Bias Prevention

| Tool | Description |
|------|-------------|
| `get_answer_guidelines` | Get constraints for bias-free answers |
| `analyze_proposed_answers` | Validate answers before creation |
| `analyze_question_quality` | Analyze single question quality |
| `analyze_exam_bias` | Aggregate bias metrics for exam |
| `get_biased_questions` | Get questions needing fixes |

### Question Editing

| Tool | Description |
|------|-------------|
| `update_question` | Update question text/metadata |
| `update_answer` | Update individual answer |
| `bulk_update_answers` | Update multiple answers |

## Recommended Workflow

1. **Get Guidelines First**: Call `get_answer_guidelines` before creating questions
2. **Draft Answers**: Follow the length constraints (all answers within 50% of each other)
3. **Validate**: Use `analyze_proposed_answers` to check for bias
4. **Create**: Only call `create_question` after validation passes

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `/data` | SQLite database directory |
| `SEED_DATA` | `true` | Seed sample data on first container run |

## Building from Source

```bash
# Build container
docker build -f Containerfile -t cert-speedrun .

# Run locally
docker run -p 8080:80 -v $(pwd)/data:/data cert-speedrun
```

## License

MIT
