from easy_quant.api.app import create_app
from tests.fakes.platform import make_test_container, make_test_settings


def create_e2e_app():
    """Playwright 专用应用：显式注入离线替身，不属于运行环境装配。"""

    settings = make_test_settings()
    return create_app(
        settings=settings,
        container=make_test_container(settings, initialize_admin=True),
    )
