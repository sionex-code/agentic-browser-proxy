# Agentic Browser Proxy

An autonomous AI-powered browser agent that can perform tasks on websites using natural language goals. Built with Playwright and integrated with LLM backends for intelligent decision-making.

## Features

- **30+ browser actions** - click, type, scroll, extract data, fill forms, and more
- **Human-like behavior** - realistic typing, random delays, error recovery
- **Skill system** - pre-configured automation recipes for specific websites
- **Profile management** - multiple browser profiles for parallel sessions
- **Duplicate tracking** - avoid repeating already completed tasks
- **Persistent memory** - learns from past sessions on each domain

## Prerequisites

- Python 3.10+
- Chrome/Chromium browser
- Windows, macOS, or Linux

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the LLM Proxy

```bash
# Terminal 1 - Start the proxy server
python glm_proxy.py
```

### 3. Run the Agent

```bash
# Terminal 2 - Run the agent
python run_agent.py "https://google.com" "search for python tutorials" 50
```

## Usage

### Generic Mode

For general website automation without a skill:

```bash
python run_agent.py "<url>" "<goal>" [max_steps]
```

**Example:**
```bash
python run_agent.py "https://amazon.com" "find shoes under $100" 50
```

### Skill Mode

For websites with pre-configured skills:

```bash
python run_agent.py --skill <skill_name> "<goal>" [max_steps]
```

**Examples:**
```bash
python run_agent.py --skill quora "answer 5 questions about python" 0
python run_agent.py --skill twitter "post a tweet about AI" 0
```

Using `0` for max_steps enables unlimited running until the skill's rules are met.

## Skill System

The `.yaser/` directory contains skill configuration files for specific websites. Each skill defines:

- **Profiles** - Multiple browser profiles for parallel sessions
- **Rules** - Answer limits, wait times, profile switching behavior
- **Selectors** - Custom CSS selectors for site-specific elements
- **Instructions** - AI instructions for that particular website

### Creating a Skill

Create a `.yaser/<site>.md` file with:

```markdown
site: quora.com
start_url: https://www.quora.com

profiles:
  - name: profile1
    cookies: []
  - name: profile2
    cookies: []

rules:
  answers_per_session: 5
  wait_between_posts_seconds: 30
  switch_profile_after: 5
  ask_user_to_login: true

tracking:
  completed_file: completed_quora.txt

selectors:
  answer_button: "a.q-text"
  submit_button: "button.q-text"

instructions: |
  Focus on unanswered questions with high views.
  Always be helpful and provide detailed answers.
```

## Available Actions

The agent can perform these actions:

| Action | Description |
|--------|-------------|
| `click` | Click an element by index |
| `type` | Type text into an input |
| `select_option` | Select from dropdown |
| `scroll` | Scroll the page |
| `goto` | Navigate to URL |
| `extract` | Extract page content |
| `wait` | Wait for specified seconds |
| `goal_completed` | Mark task as done |
| `goal_failed` | Mark task as failed |

### Skill Actions (when skill loaded)

| Action | Description |
|--------|-------------|
| `check_duplicate` | Check if URL already completed |
| `mark_completed_item` | Mark URL as completed |
| `switch_profile` | Switch to next browser profile |

## Configuration

Edit `agentic_browser_v2/config.py` to customize:

- `MAX_STEPS` - Default max steps per session
- `LONG_RUN_MODE` - Enable unlimited steps
- `VISION_FAILURE_THRESHOLD` - Screenshot capture threshold
- `YASER_DIR` - Skill files directory

## Project Structure

```
.
├── agentic_browser_v2/     # Core agent modules
│   ├── agent.py           # Main agent logic
│   ├── actions.py         # Browser actions
│   ├── prompts.py         # LLM prompts
│   ├── skill_loader.py    # Skill system
│   ├── profile_manager.py # Profile management
│   └── duplicate_tracker.py
├── glm_proxy.py           # LLM proxy server
├── proxy_api.py           # REST API server
├── run_agent.py           # Agent launcher
├── .yaser/                # Skill configurations
└── requirements.txt       # Python dependencies
```

## License

MIT
