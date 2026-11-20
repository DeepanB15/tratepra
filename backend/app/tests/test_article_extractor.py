
from app.ingestion.article_extractor import extract_article


def test_extracts_article_text():
    paragraph = (
        "Artificial intelligence research is advancing rapidly. "
        "Researchers are studying practical applications across "
        "healthcare, education, software engineering and scientific discovery. "
    )
    html = f"""
    <html>
      <head><title>Research</title></head>
      <body>
        <article>
          <h1>AI Research</h1>
          <p>{paragraph * 8}</p>
        </article>
      </body>
    </html>
    """

    result = extract_article(html)

    assert result.status == "extracted"
    assert result.text
    assert "Artificial intelligence research" in result.text


def test_returns_unavailable_for_empty_html():
    result = extract_article("<html><body></body></html>")

    assert result.text is None
    assert result.status in {"unavailable", "insufficient_content"}


def test_does_not_return_short_content():
    result = extract_article(
        "<html><body><article><p>Short text.</p></article></body></html>"
    )

    assert result.text is None
    assert result.status == "insufficient_content"
