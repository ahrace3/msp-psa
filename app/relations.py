"""Generic "related items" linking across the documentation layer — tie a
Configuration to the Credential that logs into it, a Document to the Site
it describes, and so on. One table (RelatedItem) instead of a join table
per pair of entity types.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Configuration, Credential, Document, Domain, Location, RelatedItem, SSLCertificate

# type key -> (display label, model class, attribute used as its title)
ENTITY_TYPES: dict[str, tuple[str, type, str]] = {
    "configuration": ("Configuration", Configuration, "name"),
    "credential": ("Password / Credential", Credential, "name"),
    "document": ("Document", Document, "title"),
    "location": ("Location", Location, "name"),
    "domain": ("Domain", Domain, "domain_name"),
    "ssl_certificate": ("SSL Certificate", SSLCertificate, "common_name"),
}

# type key -> where its own page lives, given the item's id
def entity_url(entity_type: str, entity_id: int, company_id: int) -> str:
    if entity_type == "configuration":
        return f"/configurations/{entity_id}/edit"
    if entity_type == "credential":
        return f"/credentials/{entity_id}/edit"
    if entity_type == "document":
        return f"/documents/{entity_id}"
    if entity_type == "location":
        return f"/locations/{entity_id}/edit"
    if entity_type == "domain":
        return f"/domains/{entity_id}/edit"
    if entity_type == "ssl_certificate":
        return f"/ssl-certificates/{entity_id}/edit"
    return f"/companies/{company_id}"


def _canonical(a_type: str, a_id: int, b_type: str, b_id: int) -> tuple[str, int, str, int]:
    """Always store the pair in the same order so (X,Y) and (Y,X) requests
    land on the same row instead of creating a duplicate reversed link."""
    pair_a, pair_b = (a_type, a_id), (b_type, b_id)
    return (*min(pair_a, pair_b), *max(pair_a, pair_b))


def link(db: Session, company_id: int, a_type: str, a_id: int, b_type: str, b_id: int) -> RelatedItem | None:
    if a_type == b_type and a_id == b_id:
        return None  # can't relate a thing to itself
    ca_type, ca_id, cb_type, cb_id = _canonical(a_type, a_id, b_type, b_id)
    existing = db.scalar(
        select(RelatedItem).where(
            RelatedItem.a_type == ca_type, RelatedItem.a_id == ca_id,
            RelatedItem.b_type == cb_type, RelatedItem.b_id == cb_id,
        )
    )
    if existing:
        return existing
    row = RelatedItem(company_id=company_id, a_type=ca_type, a_id=ca_id, b_type=cb_type, b_id=cb_id)
    db.add(row)
    db.commit()
    return row


def unlink(db: Session, relation_id: int) -> None:
    row = db.get(RelatedItem, relation_id)
    if row:
        db.delete(row)
        db.commit()


def get_related(db: Session, entity_type: str, entity_id: int, company_id: int) -> list[dict]:
    """The other side of every link involving (entity_type, entity_id),
    with a resolved display label and URL — or a "(deleted)" placeholder
    if the linked item no longer exists."""
    rows = db.scalars(
        select(RelatedItem).where(
            ((RelatedItem.a_type == entity_type) & (RelatedItem.a_id == entity_id))
            | ((RelatedItem.b_type == entity_type) & (RelatedItem.b_id == entity_id))
        )
    ).all()

    results = []
    for row in rows:
        if row.a_type == entity_type and row.a_id == entity_id:
            other_type, other_id = row.b_type, row.b_id
        else:
            other_type, other_id = row.a_type, row.a_id

        label_prefix, model, title_attr = ENTITY_TYPES.get(other_type, (other_type, None, None))
        obj = db.get(model, other_id) if model else None
        results.append({
            "relation_id": row.id,
            "type": other_type,
            "type_label": label_prefix,
            "id": other_id,
            "title": getattr(obj, title_attr) if obj else "(deleted)",
            "url": entity_url(other_type, other_id, company_id) if obj else None,
        })
    return results


def pickable_items(db: Session, company_id: int) -> list[dict]:
    """Every documentation-layer item for a company, flattened into one
    list for the "link to..." picker — labeled with its type so the same
    dropdown can offer a Configuration, a Credential, or a Document."""
    items = []
    for type_key, (label, model, title_attr) in ENTITY_TYPES.items():
        rows = db.scalars(select(model).where(model.company_id == company_id)).all()
        for obj in rows:
            items.append({
                "type": type_key, "id": obj.id,
                "label": f"[{label}] {getattr(obj, title_attr)}",
            })
    items.sort(key=lambda i: i["label"])
    return items
