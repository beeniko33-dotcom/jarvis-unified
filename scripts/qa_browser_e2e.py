#!/usr/bin/env python3
"""Authenticated browser E2E for isolated Jarvis QA Pages and Supabase.

Requires JARVIS_SUPABASE_URL and JARVIS_SUPABASE_SERVICE_ROLE_KEY in the
workflow environment. The secret key is used only by this trusted runner.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, sync_playwright

EXPECTED_QA_URL = "https://guvszwxvmitdvykvtsnc.supabase.co"
PORTAL_URL = os.environ.get("JARVIS_E2E_PORTAL_URL", "https://jarvis-unified-portal.pages.dev").rstrip("/")
CONTROL_URL = os.environ.get("JARVIS_E2E_CONTROL_URL", "https://jarvis-control-panel.pages.dev").rstrip("/")
RUN_ID = re.sub(r"[^a-zA-Z0-9-]", "-", os.environ.get("GITHUB_RUN_ID", str(int(time.time()))))
RESOURCE_ID = "qa-e2e-" + RUN_ID[:48]
OWNER_EMAIL = "jarvis-e2e-owner@example.invalid"
OPERATOR_EMAIL = "jarvis-e2e-operator@example.invalid"
REQUESTER_EMAIL = "jarvis-e2e-requester@example.invalid"
CANDIDATE_EMAIL = "jarvis-e2e-candidate@example.invalid"
EMPLOYER_EMAIL = "jarvis-e2e-employer@example.invalid"
PENDING_SELLER_EMAIL = "jarvis-e2e-pending-seller@example.invalid"
OUTSIDER_EMAIL = "jarvis-e2e-outsider@example.invalid"


class SupabaseQA:
    def __init__(self) -> None:
        self.url = os.environ.get("JARVIS_SUPABASE_URL", "").rstrip("/")
        self.secret = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if self.url != EXPECTED_QA_URL:
            raise RuntimeError("JARVIS_SUPABASE_URL must point to the isolated QA project")
        if not self.secret:
            raise RuntimeError("JARVIS_SUPABASE_SERVICE_ROLE_KEY is required")
        self.base_headers = {"apikey": self.secret, "Accept": "application/json"}
        # New Supabase secret API keys are not JWTs. Only legacy service_role
        # JWTs may be sent as Authorization bearer tokens.
        if not self.secret.startswith("sb_secret_"):
            self.base_headers["Authorization"] = "Bearer " + self.secret

    def request(self, path: str, *, method: str = "GET", body: Any = None,
                extra_headers: dict[str, str] | None = None) -> Any:
        headers = dict(self.base_headers)
        headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            # Do not include request headers, query parameters or secrets in logs.
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"Supabase {method} {urllib.parse.urlsplit(path).path} failed ({exc.code}): {detail}") from None
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            raise RuntimeError("Supabase returned a non-JSON response") from None

    def list_users(self) -> list[dict]:
        users: list[dict] = []
        for page in range(1, 21):
            result = self.request(f"/auth/v1/admin/users?page={page}&per_page=100")
            batch = result.get("users", []) if isinstance(result, dict) else []
            users.extend(batch)
            if len(batch) < 100:
                break
        return users

    def update_user(self, user_id: str, *, password: str | None = None,
                    app_metadata: dict | None = None) -> dict:
        payload: dict[str, Any] = {"email_confirm": True}
        if password:
            payload["password"] = password
        if app_metadata is not None:
            payload["app_metadata"] = app_metadata
        result = self.request(f"/auth/v1/admin/users/{urllib.parse.quote(user_id)}", method="PUT", body=payload)
        return result.get("user", result) if isinstance(result, dict) else {}

    def ensure_user(self, users: list[dict], email: str, password: str,
                    *, owner: bool = False, reset_operator: bool = False) -> dict:
        user = next((u for u in users if (u.get("email") or "").lower() == email.lower()), None)
        if user is None:
            result = self.request("/auth/v1/admin/users", method="POST", body={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"jarvis_e2e": True},
            })
            user = result.get("user", result) if isinstance(result, dict) else {}
            if not user.get("id"):
                raise RuntimeError("Supabase Auth did not return the created QA user")
            users.append(user)
        metadata = dict(user.get("app_metadata") or {})
        if owner:
            metadata["jaeo_owner"] = True
            metadata.pop("jaeo_operator", None)
        elif reset_operator:
            metadata.pop("jaeo_owner", None)
            metadata.pop("jaeo_operator", None)
        self.update_user(user["id"], password=password, app_metadata=metadata)
        user["app_metadata"] = metadata
        return {"id": user["id"], "email": email, "password": password}

    def set_roles(self, user: dict, *, owner: bool = False, operator: bool = False) -> None:
        current = next((u for u in self.list_users() if u.get("id") == user["id"]), {})
        metadata = dict(current.get("app_metadata") or {})
        if owner:
            metadata["jaeo_owner"] = True
            metadata.pop("jaeo_operator", None)
        elif operator:
            metadata["jaeo_operator"] = True
            metadata.pop("jaeo_owner", None)
        else:
            metadata.pop("jaeo_owner", None)
            metadata.pop("jaeo_operator", None)
        self.update_user(user["id"], app_metadata=metadata)

    def rest(self, table: str, *, method: str = "GET", filters: dict[str, str] | None = None,
             body: Any = None, prefer: str | None = None) -> Any:
        query = urllib.parse.urlencode(filters or {}, safe="(),.*:")
        path = "/rest/v1/" + table + (("?" + query) if query else "")
        extra = {"Accept-Profile": "public", "Content-Profile": "public"}
        if prefer:
            extra["Prefer"] = prefer
        return self.request(path, method=method, body=body, extra_headers=extra)

    def delete(self, table: str, **filters: str) -> None:
        self.rest(table, method="DELETE", filters=filters, prefer="return=minimal")

    def get_rows(self, table: str, **filters: str) -> list[dict]:
        result = self.rest(table, filters=filters)
        return result if isinstance(result, list) else []

    def insert(self, table: str, body: dict) -> dict:
        rows = self.rest(table, method="POST", body=body, prefer="return=representation")
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f"QA fixture insert into {table} returned no row")
        return rows[0]

    def seed_fixtures(self, users: dict[str, dict]) -> dict[str, str]:
        candidate = users["candidate"]["id"]
        employer = users["employer"]["id"]
        pending_seller = users["pending_seller"]["id"]
        outsider = users["outsider"]["id"]

        # Clean only rows belonging to these dedicated E2E identities.
        for order_filter in ({"buyer_id": f"eq.{candidate}"},):
            self.delete("marketplace_orders", **order_filter)
        self.delete("marketplace_affiliate_links", affiliate_user_id=f"eq.{candidate}")
        seller_rows = self.get_rows("marketplace_sellers", owner_id=f"eq.{employer}", select="id")
        for seller in seller_rows:
            listing_rows = self.get_rows("marketplace_listings", seller_id=f"eq.{seller['id']}", select="id")
            listing_ids = [row["id"] for row in listing_rows]
            self.delete("marketplace_orders", seller_id=f"eq.{seller['id']}")
            if listing_ids:
                self.delete("marketplace_affiliate_links", listing_id="in.(" + ",".join(listing_ids) + ")")
            self.delete("marketplace_listings", seller_id=f"eq.{seller['id']}")
            self.delete("marketplace_sellers", id=f"eq.{seller['id']}")
        self.delete("marketplace_sellers", owner_id=f"eq.{pending_seller}")

        # Career cleanup follows the FK dependency order for these dedicated accounts.
        self.delete("career_messages", sender_id=f"in.({candidate},{employer},{outsider})")
        apps = self.get_rows("career_applications", candidate_id=f"eq.{candidate}", select="id")
        app_ids = [row["id"] for row in apps]
        if app_ids:
            conversations = self.get_rows("career_conversations",
                application_id="in.(" + ",".join(app_ids) + ")", select="id")
            conversation_ids = [row["id"] for row in conversations]
            if conversation_ids:
                self.delete("career_messages", conversation_id="in.(" + ",".join(conversation_ids) + ")")
            self.delete("career_conversations", application_id="in.(" + ",".join(app_ids) + ")")
        self.delete("career_applications", candidate_id=f"eq.{candidate}")
        self.delete("career_jobs", created_by=f"eq.{employer}")
        self.delete("career_organizations", created_by=f"eq.{employer}")
        self.delete("career_profiles", user_id=f"in.({candidate},{employer},{outsider})")

        seller = self.insert("marketplace_sellers", {
            "owner_id": employer,
            "display_name": "Jarvis E2E Verified Store",
            "country_code": "NG",
            "description": "Dedicated isolated QA seller for browser validation.",
            "verification_status": "verified",
        })
        listing = self.insert("marketplace_listings", {
            "seller_id": seller["id"],
            "created_by": employer,
            "title": "Jarvis E2E Published Listing",
            "description": "Dedicated isolated QA listing used to validate browser order-intent creation.",
            "listing_type": "digital",
            "price": 25,
            "currency": "NGN",
            "status": "published",
            "published_at": datetime.now(timezone.utc).isoformat(),
        })
        org = self.insert("career_organizations", {
            "name": "Jarvis E2E Verified Employer",
            "description": "Dedicated isolated QA employer organization for browser validation.",
            "country_code": "NG",
            "verification_status": "verified",
            "created_by": employer,
        })
        job = self.insert("career_jobs", {
            "organization_id": org["id"],
            "created_by": employer,
            "title": "Jarvis E2E Remote Analyst",
            "description": "A dedicated remote analyst role used to test candidate applications and private HR messaging in isolated QA.",
            "employment_type": "full_time",
            "workplace_type": "remote",
            "status": "published",
            "published_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"seller_id": seller["id"], "listing_id": listing["id"],
                "organization_id": org["id"], "job_id": job["id"]}


def open_page(browser: Browser) -> Page:
    context = browser.new_context(service_workers="block", locale="en-US", timezone_id="UTC")
    page = context.new_page()
    page.set_default_timeout(30_000)
    return page


def control_panel_signin(page: Page, url: str, user: dict) -> None:
    page.goto(url, wait_until="domcontentloaded")
    configured_url = page.evaluate("window.JARVIS_CONFIG?.supabaseUrl || ''")
    if configured_url.rstrip("/") != EXPECTED_QA_URL:
        raise RuntimeError("Control-panel page is not connected to the isolated QA project")
    page.locator("#signin").wait_for(state="visible")
    page.locator("#signin-email").fill(user["email"])
    page.locator("#signin-password").fill(user["password"])
    page.locator("#signin-submit").click()
    page.locator("#app").wait_for(state="visible")


def jaeo_signin(page: Page, user: dict) -> None:
    page.goto(PORTAL_URL + "/jaeo.html", wait_until="domcontentloaded")
    configured_url = page.evaluate("window.JARVIS_CONFIG?.supabaseUrl || ''")
    if configured_url.rstrip("/") != EXPECTED_QA_URL:
        raise RuntimeError("JAEO page is not connected to the isolated QA project")
    page.locator("#auth").wait_for(state="visible")
    page.locator("#email").fill(user["email"])
    page.locator("#password").fill(user["password"])
    page.locator("#signin").click()
    page.locator("#workspace").wait_for(state="visible")


def run_marketplace(browser: Browser, qa: SupabaseQA, users: dict[str, dict], fixture: dict[str, str]) -> None:
    # Pending seller onboarding is accepted, but listing creation stays disabled.
    page = open_page(browser)
    control_panel_signin(page, CONTROL_URL + "/marketplace.html", users["pending_seller"])
    page.locator("#seller-name").fill("Jarvis E2E Pending Store")
    page.locator("#seller-country").fill("NG")
    page.locator("#seller-description").fill("Pending seller verification browser test.")
    page.locator("#submit-seller").click()
    page.locator("#seller-status").get_by_text(re.compile("pending verification", re.I)).wait_for()
    assert page.locator("#create-listing").is_disabled(), "pending seller unexpectedly enabled listing creation"
    page.context.close()

    # Verified seller creates a draft and publishes it from the browser.
    page = open_page(browser)
    control_panel_signin(page, CONTROL_URL + "/marketplace.html", users["employer"])
    title = "Jarvis E2E Browser Listing " + RUN_ID
    page.locator("#listing-title").fill(title)
    page.locator("#listing-description").fill("Browser-created listing for isolated marketplace E2E validation.")
    page.locator("#listing-price").fill("35")
    page.locator("#create-listing").click()
    page.locator("#listing-status").get_by_text(re.compile("Draft saved", re.I)).wait_for()
    page.locator("#my-listings").get_by_text(title).wait_for()
    publish = page.locator("#my-listings").locator("button[data-publish]")
    publish.first.click()
    page.locator("#listing-status").get_by_text(re.compile("Listing published", re.I)).wait_for()
    page.context.close()

    # A different authenticated user creates an order intent. This never charges or fulfils.
    page = open_page(browser)
    control_panel_signin(page, CONTROL_URL + "/marketplace.html", users["candidate"])
    listing_card = page.locator("#listing-list article.listing").filter(has_text=title)
    listing_card.wait_for()
    listing_card.locator("button[data-order]").click()
    page.locator("#listing-status").get_by_text(re.compile("Order intent created", re.I)).wait_for()
    page.locator("#listing-status").get_by_text(re.compile("No payment was taken and no reward was issued", re.I)).wait_for()
    page.locator("#orders-list").get_by_text(title).wait_for()
    page.context.close()


def run_career(browser: Browser, users: dict[str, dict]) -> None:
    candidate_message = "Candidate message " + RUN_ID
    employer_message = "HR reply " + RUN_ID

    page = open_page(browser)
    control_panel_signin(page, CONTROL_URL + "/career.html", users["candidate"])
    page.locator("#display-name").fill("E2E Candidate")
    page.locator("#headline").fill("QA Candidate")
    page.locator("#save-profile").click()
    page.locator("#profile-status").get_by_text(re.compile("Profile saved", re.I)).wait_for()
    page.locator("#job-list").get_by_text("Jarvis E2E Remote Analyst").wait_for()
    job_card = page.locator("#job-list article.item").filter(has_text="Jarvis E2E Remote Analyst")
    job_card.locator("button[data-apply]").click()
    page.locator("#message-status").get_by_text(re.compile("Application submitted", re.I)).wait_for()
    page.wait_for_function("document.querySelector('#conversation')?.value !== ''")
    page.locator("#message-body").fill(candidate_message)
    page.locator("#send-message").click()
    page.locator("#message-status").get_by_text(re.compile("Message sent", re.I)).wait_for()
    page.locator("#message-list").get_by_text(candidate_message).wait_for()
    page.context.close()

    page = open_page(browser)
    control_panel_signin(page, CONTROL_URL + "/career.html", users["employer"])
    page.locator("#application-list").get_by_text("Jarvis E2E Remote Analyst").wait_for()
    page.locator("#message-list").get_by_text(candidate_message).wait_for()
    page.locator("#message-body").fill(employer_message)
    page.locator("#send-message").click()
    page.locator("#message-status").get_by_text(re.compile("Message sent", re.I)).wait_for()
    page.locator("#message-list").get_by_text(employer_message).wait_for()
    # The verified employer can create a draft job from its own organization.
    page.locator("#create-job").wait_for()
    assert not page.locator("#create-job").is_disabled(), "verified employer could not create a draft job"
    page.locator("#job-title").fill("Jarvis E2E Employer Draft " + RUN_ID)
    page.locator("#job-description").fill("Draft job created from the authenticated employer browser workflow.")
    page.locator("#create-job").click()
    page.locator("#job-status").get_by_text(re.compile("Draft saved", re.I)).wait_for()
    page.context.close()

    page = open_page(browser)
    control_panel_signin(page, CONTROL_URL + "/career.html", users["candidate"])
    page.locator("#message-list").get_by_text(candidate_message).wait_for()
    page.locator("#message-list").get_by_text(employer_message).wait_for()
    page.context.close()

    page = open_page(browser)
    control_panel_signin(page, CONTROL_URL + "/career.html", users["outsider"])
    page.locator("#application-list").wait_for()
    assert "Jarvis E2E Remote Analyst" not in page.locator("#application-list").inner_text(), "unrelated user saw a private application"
    assert candidate_message not in page.locator("#message-list").inner_text(), "unrelated user saw a private message"
    page.context.close()


def run_jaeo(browser: Browser, qa: SupabaseQA, users: dict[str, dict]) -> str:
    # The QA owner grants the separate operator account. The UI reports the audit id.
    page = open_page(browser)
    jaeo_signin(page, users["owner"])
    page.locator("#operatorAdmin").wait_for(state="visible")
    page.locator("#operatorAdminStatus").get_by_text(re.compile("eligible account", re.I)).wait_for()
    page.locator("#operatorUser").select_option(label=users["operator"]["email"])
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#grantOperator").click()
    page.locator("#operatorAdminStatus").get_by_text(re.compile("Audit record:", re.I)).wait_for()
    admin_status = page.locator("#operatorAdminStatus").inner_text()
    match = re.search(r"Audit record:\s*([0-9a-f-]{36})", admin_status, re.I)
    if not match:
        raise AssertionError("JAEO operator grant did not expose its audit record id")
    audit_id = match.group(1)
    page.context.close()

    # Requester creates a task and requests a narrowly scoped QA approval.
    page = open_page(browser)
    jaeo_signin(page, users["requester"])
    assert "Requester" in page.locator("#role").inner_text()
    page.locator("#taskTitle").fill("QA Browser Approval " + RUN_ID)
    page.locator("#taskDescription").fill("Temporary isolated QA task for browser authorization and audit verification.")
    page.locator("#createTask").click()
    page.locator("#taskStatus").get_by_text(re.compile("Task recorded", re.I)).wait_for()
    page.locator("#approvalTask option").nth(1).wait_for()
    page.locator("#approvalTask").select_option(index=1)
    page.locator("#resourceId").fill(RESOURCE_ID)
    page.locator("#requestApproval").click()
    page.locator("#approvalStatus").get_by_text(re.compile("Approval request recorded", re.I)).wait_for()
    page.context.close()

    # Operator makes an independent approval decision; no external action is run.
    page = open_page(browser)
    jaeo_signin(page, users["operator"])
    assert "Trusted JAEO operator" in page.locator("#role").inner_text()
    approval_card = page.locator("#approvals .item").filter(has_text=RESOURCE_ID)
    approval_card.wait_for()
    approve = approval_card.locator("button[data-approve]")
    approve.wait_for()
    page.once("dialog", lambda dialog: dialog.accept("Independent QA browser approval; no external action."))
    approve.click()
    page.locator("#approvalStatus").get_by_text(re.compile("Decision recorded", re.I)).wait_for()
    approval_card = page.locator("#approvals .item").filter(has_text=RESOURCE_ID)
    approval_card.get_by_text("Decision by:").wait_for()
    approval_card.get_by_text("Decision reason: Independent QA browser approval; no external action.").wait_for()
    approval_card.get_by_text(re.compile("approved", re.I)).wait_for()
    page.context.close()

    # Requester can read the decision but never receives an approve/reject control.
    page = open_page(browser)
    jaeo_signin(page, users["requester"])
    approval_card = page.locator("#approvals .item").filter(has_text=RESOURCE_ID)
    approval_card.wait_for()
    approval_card.get_by_text("Decision by:").wait_for()
    assert approval_card.locator("[data-approve], [data-reject]").count() == 0, "requester received operator decision controls"
    page.context.close()
    return audit_id


def main() -> int:
    qa = SupabaseQA()
    run_password = secrets.token_urlsafe(32)
    users_raw = qa.list_users()
    roles = {
        "owner": qa.ensure_user(users_raw, OWNER_EMAIL, run_password, owner=True),
        "operator": qa.ensure_user(users_raw, OPERATOR_EMAIL, run_password, reset_operator=True),
        "requester": qa.ensure_user(users_raw, REQUESTER_EMAIL, run_password, reset_operator=True),
        "candidate": qa.ensure_user(users_raw, CANDIDATE_EMAIL, run_password, reset_operator=True),
        "employer": qa.ensure_user(users_raw, EMPLOYER_EMAIL, run_password, reset_operator=True),
        "pending_seller": qa.ensure_user(users_raw, PENDING_SELLER_EMAIL, run_password, reset_operator=True),
        "outsider": qa.ensure_user(users_raw, OUTSIDER_EMAIL, run_password, reset_operator=True),
    }
    results = {"marketplace": "pending", "career": "pending", "jaeo": "pending"}
    errors: list[str] = []
    browser = None
    try:
        fixtures = qa.seed_fixtures(roles)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            run_marketplace(browser, qa, roles, fixtures)
            results["marketplace"] = "passed"
            run_career(browser, roles)
            results["career"] = "passed"
            audit_id = run_jaeo(browser, qa, roles)
            results["jaeo"] = "passed"
            results["jaeo_operator_grant_audit_id"] = audit_id
            browser.close()
            browser = None
        print(json.dumps({"status": "passed", "project": "isolated QA",
                          "results": results, "run_id": RUN_ID}, indent=2))
        return 0
    except Exception as exc:
        errors.append(type(exc).__name__ + ": " + str(exc))
        print(json.dumps({"status": "failed", "project": "isolated QA",
                          "results": results, "errors": errors, "run_id": RUN_ID}, indent=2))
        return 1
    finally:
        if browser is not None:
            browser.close()
        # These short-lived test credentials are discarded after the run.
        # Remove elevated test-only claims even if a browser assertion fails.
        for role in ("owner", "operator"):
            try:
                qa.set_roles(roles[role], owner=False, operator=False)
            except Exception as cleanup_error:
                print(f"WARNING: could not demote temporary {role} QA account: {type(cleanup_error).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())
