# Product scope (V1 frozen)

Three modules: **AI Research Engine**, **Trend Intelligence Engine**, **Research Dashboard**. Four connectors (Google News, YouTube, Google Trends, Reddit) are shared infrastructure.

Out of scope for V1: MCP, autonomous agents, content generation, extra integrations, authentication (local single-user mode), Kafka/Kubernetes/Redis/Celery, a separate vector DB, microservices.

Differentiator: retrieve across sources, identify related topics, measure topic activity over time, compute an explainable Trend Score, and link every claim back to original evidence.
