import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.ai import Answer, citations
from backend.main import app


def test_auth_required():
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "online"
    for path in ["/repos", "/repos/00000000-0000-0000-0000-000000000001/file?path=README.md"]:
        assert client.get(path).status_code == 401
    assert (
        client.post("/repos", json={"url": "https://github.com/pypa/sampleproject"}).status_code
        == 401
    )


@pytest.mark.parametrize("answer,ids", [("See [S2]", [1]), ("See [S1]", [0]), ("See [S3]", [3])])
def test_unknown_citations_fail_closed(answer, ids):
    with pytest.raises(HTTPException, match="evidence"):
        citations(Answer(answer=answer, sources=ids), [{"path": "x.py"}])


def test_citations_use_only_retrieved_metadata():
    source = {"path": "alpha.py", "sha": "abc", "start_line": 2, "end_line": 4}
    result = citations(Answer(answer="See [S1]", sources=[1, 1]), [source])
    assert result["citations"] == [dict(source, label="S1")]
    assert "enough evidence" in citations(Answer(answer="unverified", sources=[]), [])["answer"]
