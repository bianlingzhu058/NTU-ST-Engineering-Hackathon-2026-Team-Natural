"""Window titles to states for Chrome and OpenOffice."""
from agent.perception import ABSENT, NEW_TAB, PRIVACY_ERROR, READY, Perception

P = Perception()


def test_chrome_states():
    assert P.page_state("Privacy error - Google Chrome", "chrome.exe") == PRIVACY_ERROR
    assert P.page_state("Apple - Google Chrome", "chrome.exe") == READY
    assert P.page_state("New Tab - Google Chrome", "chrome.exe") == NEW_TAB
    assert P.page_state("Apple - Microsoft Edge", "msedge.exe") == ABSENT


def test_writer_and_calc_share_a_process_but_not_a_title():
    assert P.is_app("writer", "Untitled 1 - OpenOffice Writer", "soffice.bin")
    assert not P.is_app("calc", "Untitled 1 - OpenOffice Writer", "soffice.bin")
    assert P.is_app("save_dialog", "Save As", "soffice.bin")
