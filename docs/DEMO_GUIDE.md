# Demo guide

1. `docker compose up --build`; make sure `ollama pull qwen2.5:7b` was run.
2. Open `http://localhost:5173/settings` and confirm which connectors are available.
3. Collect data: `python -m scripts.collect_data "AI coding agents" "LLM agents" "AI developer tools" --range 30d`.
4. Run trends: `python -m scripts.run_trend_analysis`. Re-run on later days to build history.
5. Home: metrics come from the backend. Submit "What are the emerging trends in AI coding agents?" with all sources selected.
6. Research: read the answer, click `[n]` citations, check source status and distribution.
7. Trends -> open a topic: score, component breakdown, activity history, representative records, coverage.
8. Save the research result; confirm it appears in Saved and History.

If a connector is unconfigured, say so in the demo: the UI shows it as unavailable rather than faking data.
