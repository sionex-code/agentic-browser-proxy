#!/bin/bash
# Twitter Agent Launcher - Activates venv and runs the agent
# Usage: ./twitter-agent.sh "<twitter task>" [max_steps]

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ ! -f ".venv/bin/activate" ]; then
    echo "[ERROR] Virtual environment not found!"
    echo "Please run: python run_agent.py \"x.com\" \"test\" 0"
    echo "This will create the venv automatically."
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check if task argument is provided
if [ -z "$1" ]; then
    echo "Usage: ./twitter-agent.sh \"<twitter task>\" [max_steps]"
    echo ""
    echo "Examples:"
    echo "  ./twitter-agent.sh \"search for AI accounts and follow 10\" 0"
    echo "  ./twitter-agent.sh \"post a tweet about crypto\" 0"
    echo "  ./twitter-agent.sh \"find crypto tweets and like 5 of them\" 0"
    echo ""
    exit 1
fi

# Get task and steps
TASK="$1"
STEPS="${2:-0}"  # Default to 0 (unlimited) if not provided

# Run the agent
echo "Starting Twitter Agent..."
echo "Task: $TASK"
echo "Steps: $STEPS"
echo ""

python run_agent.py "x.com" "$TASK" "$STEPS"

# Deactivate venv
deactivate

echo ""
echo "Agent finished."
