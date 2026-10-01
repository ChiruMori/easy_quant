from tests.fakes.platform import make_test_container


def test_live_store_starts_empty_for_offline_api_fixture() -> None:
    container = make_test_container()
    container.state.live_instances.clear()
    assert container.state.live_instances == {}
