from fastapi.templating import Jinja2Templates
import json
import markupsafe

from app.config import settings

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["app_name"] = settings.app_name


def money(value) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def tojson_safe(value) -> markupsafe.Markup:
    """Vanilla Jinja2 has no tojson filter (that's a Flask addition) — this
    is used to embed small server-side data structures (the ticket
    type/subtype/item tree) as JS objects inside <script> tags."""
    return markupsafe.Markup(
        json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )


templates.env.filters["money"] = money
templates.env.filters["tojson"] = tojson_safe
