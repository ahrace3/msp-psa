"""Best-effort WHOIS and SSL certificate lookups for the Domain and SSL
Certificate trackers.

Both are inherently unreliable in ways worth naming honestly: WHOIS servers
rate-limit and sometimes block automated queries, response formats vary by
registrar and TLD (a .com response looks nothing like a .io or .co.uk one),
and some registrars redact fields behind privacy proxies. Treat a lookup as
a convenient starting point to autofill a form, never as the only way to
get this data in — every field it fills stays hand-editable.

Neither of these could be tested against real servers in the sandbox this
was built in (outbound WHOIS on port 43 isn't reachable there, and outbound
HTTPS goes through an intercepting proxy that swaps in its own certificate).
The code paths are exercised and the libraries verified, but the first real
lookup on the actual server is the real test.
"""

import logging
import socket
import ssl
from datetime import date, datetime

logger = logging.getLogger("lookups")


def _first(value):
    """WHOIS responses sometimes return a list for a field that's usually
    singular (multiple 'updated' timestamps from registry transfers,
    etc.) — take the first when that happens."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _to_date(value) -> date | None:
    value = _first(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _to_str(value) -> str | None:
    value = _first(value)
    if value is None:
        return None
    return str(value).strip() or None


def whois_lookup(domain: str) -> dict:
    """Returns a dict with whatever WHOIS actually gave us. Every key is
    present; values are None when the registry didn't provide them or the
    query failed outright. Never raises — callers get a dict either way,
    with 'error' set on failure.
    """
    import whois  # imported lazily so a missing/broken install doesn't
    # break every page that merely imports this module

    result = {
        "registrar": None, "created_on": None, "updated_on": None,
        "expires_on": None, "name_servers": None, "status": None,
        "raw": None, "error": None,
    }
    try:
        w = whois.whois(domain)
    except Exception as exc:  # noqa: BLE001 - network/parsing errors, all non-fatal here
        logger.warning("whois lookup failed for %s: %r", domain, exc)
        result["error"] = str(exc)[:500]
        return result

    result["registrar"] = _to_str(w.get("registrar"))
    result["created_on"] = _to_date(w.get("creation_date"))
    result["updated_on"] = _to_date(w.get("updated_date"))
    result["expires_on"] = _to_date(w.get("expiration_date"))

    name_servers = w.get("name_servers")
    if name_servers:
        if isinstance(name_servers, (list, set)):
            result["name_servers"] = ", ".join(sorted({str(ns).lower() for ns in name_servers}))
        else:
            result["name_servers"] = str(name_servers)

    status = w.get("status")
    if status:
        if isinstance(status, list):
            result["status"] = ", ".join(str(s) for s in status)
        else:
            result["status"] = str(status)

    raw = w.get("text") or w.get("raw")
    if raw:
        result["raw"] = (raw if isinstance(raw, str) else "\n---\n".join(raw))[:8000]

    if not any([result["registrar"], result["expires_on"], result["name_servers"]]):
        result["error"] = "WHOIS responded but returned no usable fields for this domain/TLD."

    return result


def _dn(rdn_sequence, key: str) -> str | None:
    """Pull one field (e.g. 'commonName') out of the tuple-of-tuples shape
    ssl.getpeercert() returns for subject/issuer."""
    for rdn in rdn_sequence or ():
        for k, v in rdn:
            if k == key:
                return v
    return None


def ssl_lookup(hostname: str, port: int = 443, timeout: int = 10) -> dict:
    """Connects to hostname:port, completes a real TLS handshake, and reads
    the certificate the server actually presents. Never raises."""
    hostname = hostname.strip().lstrip("*.")  # a wildcard cert's own hostname doesn't resolve
    result = {
        "issued_by": None, "issued_on": None, "expires_on": None,
        "serial_number": None, "signature_algorithm": None,
        "subject_alt_names": None, "fingerprint_sha256": None, "error": None,
    }
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                der = ssock.getpeercert(binary_form=True)
    except Exception as exc:  # noqa: BLE001 - DNS, connect, and TLS errors all land here
        logger.warning("ssl lookup failed for %s: %r", hostname, exc)
        result["error"] = str(exc)[:500]
        return result

    result["issued_by"] = _dn(cert.get("issuer"), "organizationName") or _dn(cert.get("issuer"), "commonName")

    for fmt in ("%b %d %H:%M:%S %Y %Z",):
        try:
            if cert.get("notBefore"):
                result["issued_on"] = datetime.strptime(cert["notBefore"], fmt).date()
            if cert.get("notAfter"):
                result["expires_on"] = datetime.strptime(cert["notAfter"], fmt).date()
        except ValueError:
            pass

    result["serial_number"] = cert.get("serialNumber")

    sans = cert.get("subjectAltName") or ()
    dns_names = [v for k, v in sans if k == "DNS"]
    if dns_names:
        result["subject_alt_names"] = ", ".join(dns_names)

    if der:
        try:
            import hashlib
            result["fingerprint_sha256"] = hashlib.sha256(der).hexdigest()
        except Exception:  # noqa: BLE001 - fingerprint is a nice-to-have, never fatal
            pass
        try:
            from cryptography import x509
            parsed = x509.load_der_x509_certificate(der)
            result["signature_algorithm"] = parsed.signature_algorithm_oid._name
        except Exception:  # noqa: BLE001 - already have the essentials from getpeercert()
            pass

    return result
