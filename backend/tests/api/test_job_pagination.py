from datetime import timedelta

import pytest

from easy_quant.api.app import create_app
from easy_quant.domain.scheduling.entities import Job
from tests.fakes.platform import make_test_container


def test_jobs_use_server_pagination_descending_time_and_stable_ties():
    container = make_test_container(initialize_admin=True)
    now = container.authentication.clock.now()
    for index in range(45):
        container.jobs.enqueue(
            Job(
                f"job-{index:02}",
                "demo",
                str(index),
                {"secret": "hidden"},
                now + timedelta(minutes=index // 2),
            )
        )
    client = create_app(container=container, settings=container.settings).test_client()
    assert client.get("/api/v1/admin/jobs").status_code == 401
    client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "change-this-admin-password"}
    )
    first = client.get("/api/v1/admin/jobs").get_json()["data"]
    second = client.get("/api/v1/admin/jobs?page=2").get_json()["data"]
    last = client.get("/api/v1/admin/jobs?page=999999999").get_json()["data"]
    assert (first["total"], first["page_size"], len(first["items"])) == (45, 20, 20)
    assert [item["id"] for item in first["items"] + second["items"] + last["items"]] == [
        f"job-{index:02}" for index in range(44, -1, -1)
    ]
    assert last["page"] == 3
    assert "hidden" not in str(first)


@pytest.mark.parametrize(
    "query", ["page=0", "page=-1", "page=bad", "page_size=0", "page_size=101", "page_size=bad"]
)
def test_invalid_job_pagination_is_rejected(query):
    container = make_test_container(initialize_admin=True)
    client = create_app(container=container, settings=container.settings).test_client()
    client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "change-this-admin-password"}
    )
    assert client.get(f"/api/v1/admin/jobs?{query}").status_code == 400


def test_empty_jobs_have_first_page():
    container = make_test_container()
    assert container.jobs.list_page(999, 20) == ([], 0, 1)
