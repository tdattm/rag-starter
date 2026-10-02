from unittest.mock import patch

import pytest

from backend.ingestion import Passage, fetch_web, public_address, split_passages
from backend.rag import bm25_scores, tokenize
from backend.store import Store


def test_chunking_keeps_overlap_page_and_all_text():
    text = "abcdefghijklmnopqrstuvwxyz" * 100
    chunks = split_passages([Passage(text, 3)], 200, 30)
    assert all(len(item.text) <= 200 and item.page == 3 for item in chunks)
    assert chunks[0].text[-30:] == chunks[1].text[:30]
    assert chunks[-1].text.endswith(text[-20:])


def test_unicode_search_matches_unaccented_vietnamese():
    assert tokenize("Tích phân và Đại số") == tokenize("tich phan va dai so")
    scores = bm25_scores("tich phan", ["Tích phân suy rộng", "Lịch sử địa lý"])
    assert scores[0] > 0 and scores[1] == 0


def test_document_and_chat_persist_after_restart(tmp_path):
    path = tmp_path / "persistent.db"
    store = Store(path)
    chat = store.create_conversation()
    store.message(chat["id"], "user", "Xin chào")
    restarted = Store(path)
    assert restarted.conversation(chat["id"])["messages"][0]["content"] == "Xin chào"


def test_mixed_public_private_dns_is_blocked():
    with patch(
        "socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("127.0.0.1", 443))],
    ):
        with pytest.raises(ValueError, match="nội bộ"):
            public_address("https://example.com")


def test_redirect_to_private_address_is_blocked():
    class Redirect:
        status = 302

        def getheader(self, name, default=None):
            return "http://127.0.0.1/secret" if name == "Location" else default

    with patch("backend.ingestion.PinnedHTTPSConnection") as connection:
        connection.return_value.getresponse.return_value = Redirect()
        with patch(
            "socket.getaddrinfo",
            side_effect=[[(2, 1, 6, "", ("93.184.216.34", 443))], [(2, 1, 6, "", ("127.0.0.1", 80))]],
        ):
            with pytest.raises(ValueError, match="nội bộ"):
                fetch_web("https://example.com", 10000)
