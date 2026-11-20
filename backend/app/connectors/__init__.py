from app.connectors.base import BaseConnector
from app.connectors.google_news import GoogleNewsConnector
from app.connectors.google_trends import GoogleTrendsConnector
from app.connectors.reddit import RedditConnector
from app.connectors.youtube import YouTubeConnector

CONNECTOR_CLASSES: dict[str, type[BaseConnector]] = {
    "google_news": GoogleNewsConnector,
    "youtube": YouTubeConnector,
    "google_trends": GoogleTrendsConnector,
    "reddit": RedditConnector,
}


def get_connector(key: str) -> BaseConnector:
    return CONNECTOR_CLASSES[key]()


def all_connectors() -> list[BaseConnector]:
    return [cls() for cls in CONNECTOR_CLASSES.values()]
