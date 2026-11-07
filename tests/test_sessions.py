from handlers.files import _collection_files


def test_fresh_upload_without_session_has_no_collected_files():
    assert _collection_files(None, None) == []
    assert _collection_files(None, "zip_collect") == []


def test_collection_lookup_selects_the_correct_session_list():
    session = {
        "merge_files": ["a.pdf"],
        "zip_files": ["a.txt", "b.png"],
        "image_files": ["a.png", "b.jpg"],
    }
    assert _collection_files(session, "merge_collect") == ["a.pdf"]
    assert _collection_files(session, "zip_collect") == ["a.txt", "b.png"]
    assert _collection_files(session, "image_pdf_collect") == ["a.png", "b.jpg"]
    assert _collection_files(session, None) == []
