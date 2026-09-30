"""Démo « marque blanche » pour un prospect : le scénario fictif complet, dans une organisation à son nom.

Reprend le scénario de démonstration principal (équipe, 6 PME fictives, diagnostics, documents, plan, rapports)
dans une organisation distincte, avec des comptes dédiés ``<prénom.rôle>.<slug>@demo.test`` : aucune donnée ni
aucun nom de l'organisation de démonstration d'origine n'y apparaît.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace

from seeds import demo

SOURCE = "pme360-demo"


def account(email: str, slug: str) -> str:
    local = email.split("@", 1)[0]
    return f"{local}.{slug}@demo.test"


def build(
    slug: str,
    name: str,
    *,
    short_name: str,
    product_name: str = "PME360",
    color: str = "#2E4A6B",
    logo: str | None = None,
    org_type: str = "BANQUE",
) -> SimpleNamespace:
    branding = {"product_name": product_name, "short_name": short_name, "primary_color": color}
    if logo:
        branding["logo"] = logo
    users = [
        (account(email, slug), full_name, slug, role, scope, ref)
        for email, full_name, org, role, scope, ref in demo.USERS
        if org == SOURCE
    ]
    pmes = []
    for spec in demo.PMES:
        if spec["org"] != SOURCE:
            continue
        item = copy.deepcopy(spec)
        item["org"] = slug
        for key in ("advisor", "expert"):
            if item.get(key):
                item[key] = account(item[key], slug)
        if item["data"].get("email"):
            item["data"]["email"] = item["data"]["email"].replace(".demo.test", f".{slug}.demo.test")
        pmes.append(item)
    return SimpleNamespace(
        ORGANIZATIONS=[{"slug": slug, "name": name, "type": org_type, "branding": branding}],
        USERS=users,
        PMES=pmes,
        PROGRAMME=demo.PROGRAMME,
        LIFECYCLE_PATH=demo.LIFECYCLE_PATH,
        DEMO_PASSWORD=demo.DEMO_PASSWORD,
        PRIMARY=slug,
    )
