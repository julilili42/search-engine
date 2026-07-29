from tuebingen_search.models import Document, SearchIndex
from tuebingen_search.storage import load_index, save_index


def test_load_index_resolves_project_relative_document_paths(tmp_path, monkeypatch):
    project = tmp_path / "project"
    page = project / "data/html/page.html"
    page.parent.mkdir(parents=True)
    page.write_text("content", encoding="utf-8")
    index_path = tmp_path / "index.bin"
    save_index(
        index_path,
        SearchIndex(
            documents=[
                Document(
                    path=page.relative_to(project),
                    url="https://example.test",
                    length=1,
                    terms=("content",),
                )
            ],
            inverted_index={},
        ),
    )

    monkeypatch.setattr("tuebingen_search.storage.PROJECT_ROOT", project)
    monkeypatch.chdir(tmp_path)

    assert load_index(index_path).documents[0].path == page
