"""Nomenclatures par défaut copiées dans chaque nouvelle organisation (modifiables ensuite par l'ADMIN_ORG).

Ce sont des listes de référence, pas des règles réglementaires. À faire confirmer par GUDE-PME :
- découpage administratif (31 régions + 2 districts autonomes) ;
- nomenclature sectorielle (alignement éventuel sur une nomenclature officielle d'activités).
"""

SECTORS: list[tuple[str, str]] = [
    ("COMMERCE", "Commerce et distribution"),
    ("INDUSTRIE", "Industrie et transformation"),
    ("BTP", "Bâtiment et travaux publics"),
    ("SERVICES", "Services aux entreprises et aux particuliers"),
    ("AGROALIMENTAIRE", "Agroalimentaire"),
    ("AGRICULTURE", "Agriculture, élevage et pêche"),
    ("TECH", "Startup technologique et numérique"),
    ("TRANSPORT", "Transport et logistique"),
    ("TOURISME", "Tourisme, hôtellerie et restauration"),
    ("SANTE", "Santé et pharmacie"),
    ("EDUCATION", "Éducation et formation"),
    ("ARTISANAT", "Artisanat"),
    ("ENERGIE", "Énergie et environnement"),
    ("MINES", "Mines et carrières"),
    ("AUTRE", "Autre"),
]

# (code, libellé, société ?) — formes de l'Acte uniforme OHADA et statut de l'entreprenant.
LEGAL_FORMS: list[tuple[str, str, bool]] = [
    ("ENTREPRENANT", "Entreprenant", False),
    ("EI", "Entreprise individuelle", False),
    ("SARL", "Société à responsabilité limitée (SARL)", True),
    ("SARLU", "SARL unipersonnelle (SARLU)", True),
    ("SA", "Société anonyme (SA)", True),
    ("SAS", "Société par actions simplifiée (SAS)", True),
    ("SASU", "SAS unipersonnelle (SASU)", True),
    ("SNC", "Société en nom collectif (SNC)", True),
    ("SCS", "Société en commandite simple (SCS)", True),
    ("GIE", "Groupement d'intérêt économique (GIE)", True),
    ("SCOOPS", "Société coopérative simplifiée (SCOOPS)", True),
    ("SCOOP_CA", "Société coopérative avec conseil d'administration", True),
    ("AUTRE", "Autre", True),
]

DISTRICTS: list[tuple[str, str]] = [
    ("ABIDJAN", "District autonome d'Abidjan"),
    ("YAMOUSSOUKRO", "District autonome de Yamoussoukro"),
]

REGIONS: list[tuple[str, str]] = [
    ("AGNEBY_TIASSA", "Agnéby-Tiassa"),
    ("BAFING", "Bafing"),
    ("BAGOUE", "Bagoué"),
    ("BELIER", "Bélier"),
    ("BERE", "Béré"),
    ("BOUNKANI", "Bounkani"),
    ("CAVALLY", "Cavally"),
    ("FOLON", "Folon"),
    ("GBEKE", "Gbêkê"),
    ("GBOKLE", "Gbôklé"),
    ("GOH", "Gôh"),
    ("GONTOUGO", "Gontougo"),
    ("GRANDS_PONTS", "Grands-Ponts"),
    ("GUEMON", "Guémon"),
    ("HAMBOL", "Hambol"),
    ("HAUT_SASSANDRA", "Haut-Sassandra"),
    ("IFFOU", "Iffou"),
    ("INDENIE_DJUABLIN", "Indénié-Djuablin"),
    ("KABADOUGOU", "Kabadougou"),
    ("LA_ME", "La Mé"),
    ("LOH_DJIBOUA", "Lôh-Djiboua"),
    ("MARAHOUE", "Marahoué"),
    ("MORONOU", "Moronou"),
    ("NAWA", "Nawa"),
    ("NZI", "N'Zi"),
    ("PORO", "Poro"),
    ("SAN_PEDRO", "San-Pédro"),
    ("SUD_COMOE", "Sud-Comoé"),
    ("TCHOLOGO", "Tchologo"),
    ("TONKPI", "Tonkpi"),
    ("WORODOUGOU", "Worodougou"),
]


def install_defaults(organization) -> None:
    """Copie idempotente des nomenclatures dans ``organization`` (appelée à la création du tenant)."""
    from .models import LegalForm, Region, Sector

    for order, (code, name) in enumerate(SECTORS):
        Sector.objects.get_or_create(organization=organization, code=code, defaults={"name": name, "order": order})
    for order, (code, name, is_company) in enumerate(LEGAL_FORMS):
        LegalForm.objects.get_or_create(
            organization=organization, code=code, defaults={"name": name, "order": order, "is_company": is_company}
        )
    for order, (code, name) in enumerate(DISTRICTS):
        Region.objects.get_or_create(
            organization=organization,
            code=code,
            defaults={"name": name, "order": order, "kind": Region.Kind.DISTRICT_AUTONOME},
        )
    for order, (code, name) in enumerate(REGIONS, start=len(DISTRICTS)):
        Region.objects.get_or_create(organization=organization, code=code, defaults={"name": name, "order": order})
