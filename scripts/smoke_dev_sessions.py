"""Exercise the deployed DEV API with two short-lived Clerk test-user tokens."""

import os
from urllib.parse import urlparse

import httpx


def main():
    """Verify deployed persistence and isolation using disposable DEV accounts.

    Use a dedicated owner with no concurrent activity so history order assertions
    are deterministic. Tokens must belong to different users, not merely be two
    tokens from one account; foreign-access assertions verify that distinction.
    Cleanup is attempted even on failure, but expired tokens or storage outages
    can leave synthetic records requiring manual removal after recovery.
    """
    base_url = os.environ["DEV_API_BASE_URL"].rstrip("/")
    if urlparse(base_url).hostname != "api-dev.veenoe.com" or not base_url.startswith(
        "https://"
    ):
        raise RuntimeError("Smoke test is restricted to https://api-dev.veenoe.com")
    owner_token = os.environ["DEV_OWNER_TOKEN"]
    other_token = os.environ["DEV_OTHER_TOKEN"]
    if not owner_token or not other_token or owner_token == other_token:
        raise RuntimeError("Two distinct valid DEV Clerk user tokens are required")
    created = []
    with httpx.Client(
        base_url=base_url,
        timeout=30,
        headers={"Authorization": f"Bearer {owner_token}"},
    ) as client:

        def call(method, path, expected=200, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.status_code != expected:
                # Never print response bodies, headers, tokens, or child data.
                raise RuntimeError(
                    f"Smoke {method} failed: expected {expected}, got {response.status_code}"
                )
            return response.json()

        try:
            call("GET", "/health")
            for _ in range(2):
                result = call(
                    "POST",
                    "/api/v1/viva/start",
                    json={
                        "student_name": "Synthetic smoke user",
                        "topic": "Plants",
                        "class_level": "7",
                    },
                )
                created.append(result["viva_session_id"])
            first, newest = created
            detail = call("GET", f"/api/v1/viva/{first}")
            assert detail["status"] == "in_progress"
            foreign_headers = {"Authorization": f"Bearer {other_token}"}
            call("GET", f"/api/v1/viva/{first}", expected=404, headers=foreign_headers)
            call(
                "PATCH",
                f"/api/v1/viva/{first}/rename",
                expected=404,
                headers=foreign_headers,
                json={"new_title": "Must not persist"},
            )
            call(
                "PATCH",
                f"/api/v1/viva/{first}/rename",
                json={"new_title": "DEV smoke renamed"},
            )
            call(
                "POST",
                "/api/v1/viva/conclude-viva",
                json={
                    "viva_session_id": first,
                    "score": 8,
                    "summary": "Synthetic smoke assessment",
                    "strong_points": [],
                    "areas_of_improvement": [],
                    "transcript": "Synthetic teacher: Why?\nSynthetic student: Light.",
                },
            )
            detail = call("GET", f"/api/v1/viva/{first}")
            assert detail["status"] == "completed" and detail["feedback"]["score"] == 8
            assert detail["title"] == "DEV smoke renamed" and detail["transcript"]
            history = call("GET", "/api/v1/viva/history", params={"limit": 1})
            assert history["sessions"][0]["viva_session_id"] == newest
            older = call(
                "GET",
                "/api/v1/viva/history",
                params={"limit": 1, "cursor": history["next_cursor"]},
            )
            assert older["sessions"][0]["viva_session_id"] == first
            assert (
                call("POST", f"/api/v1/viva/{newest}/abandon")["status"] == "abandoned"
            )
        finally:
            for identifier in created:
                call("DELETE", f"/api/v1/viva/{identifier}")
        print(
            "DEV DynamoDB API smoke passed: create/read/update/history/pagination/ownership/delete."
        )


if __name__ == "__main__":
    main()
