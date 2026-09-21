"""Microsoft Graph client for the shared support mailbox.

Client-credentials (app-only) flow against a shared mailbox that has no
license and no interactive user, so there's no refresh token to keep alive
— every poll fetches a fresh app token. This makes outbound-only polling
work behind NAT: nothing needs to reach the NAS.

Unread mail is the queue. We fetch unread messages, process them, then mark
each one read. If the worker crashes mid-batch, whatever wasn't marked read
gets reprocessed next poll — duplicate tickets are prevented by graph_id
being unique on EmailMessage, so a re-run just re-marks it read and moves on.
"""

import re

import httpx

from app.config import settings

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TMPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

TICKET_TOKEN_RE = re.compile(r"\[#(\d{5,7})\]")


class GraphNotConfigured(Exception):
    pass


def _require_config() -> None:
    if not (settings.graph_tenant_id and settings.graph_client_id and settings.graph_client_secret):
        raise GraphNotConfigured(
            "GRAPH_TENANT_ID / GRAPH_CLIENT_ID / GRAPH_CLIENT_SECRET are not set"
        )


def get_access_token() -> str:
    _require_config()
    resp = httpx.post(
        TOKEN_URL_TMPL.format(tenant=settings.graph_tenant_id),
        data={
            "client_id": settings.graph_client_id,
            "client_secret": settings.graph_client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_unread(token: str, mailbox: str, top: int = 25) -> list[dict]:
    resp = httpx.get(
        f"{GRAPH_BASE}/users/{mailbox}/mailFolders/inbox/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "$filter": "isRead eq false",
            "$orderby": "receivedDateTime asc",
            "$top": top,
            "$select": (
                "id,subject,from,receivedDateTime,internetMessageId,"
                "bodyPreview,body,conversationId"
            ),
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("value", [])


def mark_read(token: str, mailbox: str, message_id: str) -> None:
    resp = httpx.patch(
        f"{GRAPH_BASE}/users/{mailbox}/messages/{message_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"isRead": True},
        timeout=15,
    )
    resp.raise_for_status()


def extract_ticket_number(subject: str) -> str | None:
    match = TICKET_TOKEN_RE.search(subject or "")
    return match.group(1) if match else None


def clean_body(message: dict) -> str:
    """HTML bodies get the tags stripped crudely — good enough for a ticket
    note; not meant to be a full HTML-to-text pipeline."""
    body = message.get("body", {})
    content = body.get("content", "") or message.get("bodyPreview", "")
    if body.get("contentType") == "html":
        content = re.sub(r"<[^>]+>", " ", content)
        content = re.sub(r"\s+", " ", content).strip()
    return content[:5000]
