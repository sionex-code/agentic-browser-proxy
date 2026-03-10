---
name: twitter-agent
description: Autonomous AI agent for Twitter/X. Can search, follow, post, like, retweet, reply, DM, and do anything on Twitter automatically.
homepage: https://x.com
metadata:
  {
    "openclaw":
      {
        "emoji": "🐦",
        "os": ["win32"],
        "requires": { "bins": ["python"] },
      },
  }
---

# Twitter Agent

Autonomous AI agent that can do **anything** on Twitter/X — search, follow, post, like, retweet, reply, DM, read threads, extract data, and more.

## Run

```batch
{baseDir}\twitter-agent.bat "<your twitter task>" 0
```

The second argument is max steps. Use `0` for unlimited (recommended).

## Examples

```batch
{baseDir}\twitter-agent.bat "search for AI agentic accounts and follow 10 of them" 0
{baseDir}\twitter-agent.bat "post a tweet: Hello world! #AI #Twitter" 0
{baseDir}\twitter-agent.bat "search for crypto tweets, like the top 5, and follow their authors" 0
{baseDir}\twitter-agent.bat "find tweets about Python programming and reply to 3 with helpful tips" 0
{baseDir}\twitter-agent.bat "search for AI news and retweet the top 5 posts" 0
{baseDir}\twitter-agent.bat "search for crypto accounts, follow 3, then DM one saying hello" 0
```

## What It Can Do

Everything you can do manually on Twitter:

- Search for users, hashtags, topics, tweets
- Follow/unfollow accounts in bulk
- Post tweets, threads, polls
- Like, retweet, quote tweet
- Reply to tweets and threads
- Send and read Direct Messages
- Read timelines, profiles, threads
- Extract and analyze data from tweets
- Navigate all sections (Home, Explore, Notifications, Messages, Lists, etc.)
- Manage Twitter Lists, update profile, bookmark, mute, block

## Task Format

Structure tasks as clear instructions:

- **Good:** `"search for crypto accounts and follow 10"`
- **Good:** `"post a tweet about AI with hashtags #AI #MachineLearning"`
- **Bad:** `"go to google.com"` (not Twitter)
- **Bad:** `"just browse"` (not specific enough)

## First Run

1. Run any task — browser opens to x.com
2. If not logged in, log in manually
3. Press Ctrl+C, then run again — session is saved

## Output

- `memory_session_YYYYMMDD_HHMMSS.txt` — full action history and learned lessons
- Agent runs in visible browser window so you can watch
- Press Ctrl+C to stop anytime
