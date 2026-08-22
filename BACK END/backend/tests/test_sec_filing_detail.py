from intelligence.providers.sec_filing_detail import _candidate_document_links, html_to_text


def test_html_to_text_removes_scripts_and_styles():
    document = """
    <html><head><style>.hidden {display:none}</style><script>alert('x')</script></head>
    <body><h1>Risk Factors</h1><p>Revenue declined 12%.</p></body></html>
    """
    text = html_to_text(document)
    assert "Risk Factors" in text
    assert "Revenue declined 12%." in text
    assert "alert" not in text
    assert "display:none" not in text


def test_candidate_document_links_prefers_real_html_documents():
    index_html = """
    <a href="/Archives/edgar/data/123/filing-index.html">Index</a>
    <a href="/Archives/edgar/data/123/primary.htm">Primary</a>
    <a href="javascript:void(0)">Ignore</a>
    <a href="/ixviewer/doc.htm">Viewer</a>
    """
    links = _candidate_document_links(index_html, "https://www.sec.gov/Archives/edgar/data/123/")
    assert "https://www.sec.gov/Archives/edgar/data/123/primary.htm" in links
    assert all("javascript:" not in link for link in links)
    assert all("ixviewer" not in link for link in links)
