"""Import en masse des PME par fichier CSV (Document 10, V1) : aperçu sans écriture, puis création des lignes valides.

Chaque ligne passe par les mêmes règles que la saisie manuelle (sérialiseur de création, normalisation des
identifiants, détection de doublons) ; aucune donnée n'est créée à l'aperçu. Les doublons d'identifiant (RCCM, NCC)
sont toujours écartés ; les raisons sociales proches ne sont importées que sur confirmation explicite.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from django.db import transaction
from rest_framework.exceptions import ValidationError

from pme360.core.exceptions import BusinessError

MAX_ROWS = 2000
MAX_BYTES = 2 * 1024 * 1024

# Colonne du fichier → champ ; les en-têtes sont comparés sans accents, espaces ni casse.
COLUMNS = [
    ("raison_sociale", "Raison sociale (obligatoire)", "Boutique Exemple SARL"),
    ("nom_commercial", "Nom commercial", "Boutique Exemple"),
    ("forme_juridique", "Forme juridique (code ou libellé)", "SARL"),
    ("rccm", "Numéro RCCM", "CI-ABJ-2019-B-12345"),
    ("ncc", "Numéro de compte contribuable (NCC)", "1234567A"),
    ("cnps", "Numéro employeur CNPS", "123456"),
    ("date_creation", "Date de création (JJ/MM/AAAA)", "15/03/2019"),
    ("secteur", "Secteur (code ou libellé)", "COMMERCE"),
    ("region", "Région (code ou libellé)", "ABIDJAN"),
    ("commune", "Commune", "Cocody"),
    ("adresse", "Adresse", "Rue des Jardins"),
    ("telephone", "Téléphone", "+225 07 00 00 00 00"),
    ("email", "E-mail", "contact@exemple.ci"),
    ("site_web", "Site web", ""),
    ("effectif", "Effectif", "12"),
    ("dirigeant_nom", "Nom du dirigeant", "Awa Koné"),
    ("dirigeant_fonction", "Fonction du dirigeant (GERANT, DG, PDG…)", "GERANT"),
    ("dirigeant_telephone", "Téléphone du dirigeant", ""),
    ("dirigeant_email", "E-mail du dirigeant", ""),
    ("conseiller_email", "E-mail du conseiller principal", ""),
]
FIELD_MAP = {
    "raison_sociale": "legal_name",
    "nom_commercial": "trade_name",
    "rccm": "rccm_number",
    "ncc": "ncc",
    "cnps": "cnps_employer_number",
    "commune": "commune",
    "adresse": "address",
    "telephone": "phone",
    "email": "email",
    "site_web": "website",
}
ALIASES = {
    "raisonsociale": "raison_sociale",
    "denomination": "raison_sociale",
    "nom": "raison_sociale",
    "nomcommercial": "nom_commercial",
    "sigle": "nom_commercial",
    "formejuridique": "forme_juridique",
    "numerorccm": "rccm",
    "registreducommerce": "rccm",
    "numerodecomptecontribuable": "ncc",
    "comptecontribuable": "ncc",
    "numeroemployeurcnps": "cnps",
    "cnpsemployeur": "cnps",
    "datedecreation": "date_creation",
    "datecreation": "date_creation",
    "tel": "telephone",
    "courriel": "email",
    "mail": "email",
    "siteweb": "site_web",
    "siteinternet": "site_web",
    "nombredesalaries": "effectif",
    "salaries": "effectif",
    "nomdudirigeant": "dirigeant_nom",
    "dirigeant": "dirigeant_nom",
    "fonctiondudirigeant": "dirigeant_fonction",
    "telephonedudirigeant": "dirigeant_telephone",
    "emaildudirigeant": "dirigeant_email",
    "conseiller": "conseiller_email",
    "emailduconseiller": "conseiller_email",
}
ROLE_ALIASES = {"PDG": "DG", "DIRECTEURGENERAL": "DG", "GERANTE": "GERANT", "PRESIDENTE": "PRESIDENT"}


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def canonical_header(header: str) -> str | None:
    key = _fold(header.split("(")[0])
    known = {_fold(c): c for c, _, _ in COLUMNS}
    known.update({_fold(label.split("(")[0]): c for c, label, _ in COLUMNS})  # libellés du modèle
    return known.get(key) or ALIASES.get(key)


def template_csv() -> str:
    """Modèle téléchargeable : en-têtes lisibles + une ligne d'exemple (fictive)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([label for _, label, _ in COLUMNS])
    writer.writerow([example for _, _, example in COLUMNS])
    return "﻿" + buffer.getvalue()


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise BusinessError("Encodage du fichier non reconnu : enregistrez-le en CSV UTF-8.", code="invalid_encoding")


def read_rows(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Lit le fichier (séparateur ; ou , détecté) et renvoie les colonnes reconnues et les lignes non vides."""
    if len(content) > MAX_BYTES:
        raise BusinessError("Fichier trop volumineux (2 Mo au maximum).", code="file_too_large")
    text = _decode(content)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";"
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        headers = next(reader)
    except StopIteration as exc:
        raise BusinessError("Le fichier est vide.", code="empty_file") from exc
    mapping = [canonical_header(h) for h in headers]
    if "raison_sociale" not in mapping:
        raise BusinessError(
            "Colonne « Raison sociale » introuvable : utilisez le modèle de fichier.", code="missing_columns"
        )
    rows = []
    for values in reader:
        if not any(v.strip() for v in values):
            continue
        rows.append({col: values[i].strip() for i, col in enumerate(mapping) if col and i < len(values)})
    if len(rows) > MAX_ROWS:
        raise BusinessError(f"{MAX_ROWS} lignes au maximum par import.", code="too_many_rows")
    return [c for c in mapping if c], rows


def _date(value: str) -> date | None:
    for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValueError(value)


@dataclass
class RowResult:
    line: int
    legal_name: str
    status: str  # VALIDE | DOUBLON_PROBABLE | ERREUR | CREEE | IGNOREE
    errors: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)
    pme_id: str | None = None
    data: dict = field(default_factory=dict, repr=False)
    extras: dict = field(default_factory=dict, repr=False)


class References:
    """Nomenclatures de l'organisation, résolues par code ou par libellé (sans accents ni casse)."""

    def __init__(self):
        from pme360.accounts.models import User

        from .models import LegalForm, Region, Sector

        self.tables = {
            "forme_juridique": ("legal_form", self._index(LegalForm.objects.all())),
            "secteur": ("sector", self._index(Sector.objects.filter(is_active=True))),
            "region": ("region", self._index(Region.objects.filter(is_active=True))),
        }
        self.users = {u.email.lower(): u for u in User.objects.filter(is_active=True)}

    @staticmethod
    def _index(queryset) -> dict[str, object]:
        index = {}
        for item in queryset:
            index[_fold(item.code)] = item
            index[_fold(item.name)] = item
        return index

    def resolve(self, column: str, value: str):
        return self.tables[column][1].get(_fold(value))


def _build(row: dict[str, str], refs: References, line: int) -> RowResult:
    from .models import PmePerson

    result = RowResult(line=line, legal_name=row.get("raison_sociale", ""), status="VALIDE")
    data: dict = {target: row[source] for source, target in FIELD_MAP.items() if row.get(source)}
    for column, (target, _) in refs.tables.items():
        if row.get(column):
            item = refs.resolve(column, row[column])
            if item is None:
                result.errors[column] = f"« {row[column]} » n'existe pas dans la nomenclature."
            else:
                data[target] = item.pk
    if row.get("date_creation"):
        try:
            data["creation_date"] = _date(row["date_creation"]).isoformat()
        except ValueError:
            result.errors["date_creation"] = "Date illisible (format attendu : JJ/MM/AAAA)."
    if row.get("effectif"):
        try:
            data["headcount"] = int(float(row["effectif"].replace(" ", "").replace(",", ".")))
        except ValueError:
            result.errors["effectif"] = "L'effectif doit être un nombre."
    if row.get("dirigeant_nom"):
        role = _fold(row.get("dirigeant_fonction", "")).upper()
        role = ROLE_ALIASES.get(role, role) or PmePerson.Role.GERANT
        if role not in PmePerson.Role.values:
            result.errors["dirigeant_fonction"] = (
                "Fonction inconnue (GERANT, DG, PCA, PRESIDENT, ASSOCIE, DIRECTEUR, CONTACT)."
            )
        else:
            result.extras["primary_person"] = {
                "full_name": row["dirigeant_nom"],
                "role": role,
                "phone": row.get("dirigeant_telephone", ""),
                "email": row.get("dirigeant_email", ""),
            }
    if row.get("conseiller_email"):
        advisor = refs.users.get(row["conseiller_email"].lower())
        if advisor is None:
            result.errors["conseiller_email"] = "Aucun utilisateur actif avec cet e-mail."
        else:
            result.extras["advisor_id"] = advisor.pk
    result.data = data
    return result


def analyze(access, content: bytes) -> tuple[list[str], list[RowResult]]:
    """Aperçu : valide chaque ligne et repère les doublons, sans rien écrire."""
    from . import services
    from .serializers import PersonSerializer, PmeCreateSerializer

    columns, rows = read_rows(content)
    refs = References()
    results = []
    seen: dict[str, int] = {}
    for index, row in enumerate(rows, start=2):  # ligne 1 : en-têtes
        result = _build(row, refs, index)
        serializer = PmeCreateSerializer(data=result.data)
        if not serializer.is_valid():
            for key, messages in serializer.errors.items():
                result.errors.setdefault(key, " ".join(str(m) for m in messages))
        else:
            # Champs annexes gérés à part (dirigeant, conseiller, cohorte), comme la saisie manuelle.
            excluded = {"primary_person", "advisor_id", "cohort_id", "confirm_duplicates", "start_onboarding"}
            result.data = {k: v for k, v in serializer.validated_data.items() if k not in excluded}
        if "primary_person" in result.extras:
            person = PersonSerializer(data=result.extras["primary_person"])
            if not person.is_valid():
                for key, messages in person.errors.items():
                    result.errors.setdefault(f"dirigeant_{key}", " ".join(str(m) for m in messages))
        if result.errors:
            result.status = "ERREUR"
            results.append(result)
            continue
        # Doublons dans le fichier (mêmes identifiants ou même raison sociale).
        keys = [
            f"rccm:{services.normalize_rccm(row.get('rccm', ''))}" if row.get("rccm") else None,
            f"ncc:{services.normalize_compact(row.get('ncc', ''))}" if row.get("ncc") else None,
            f"nom:{_fold(result.legal_name)}",
        ]
        repeated = [seen[k] for k in keys if k and k in seen]
        if repeated:
            result.status = "ERREUR"
            result.errors["fichier"] = f"Même entreprise qu'à la ligne {repeated[0]} du fichier."
            results.append(result)
            continue
        for key in keys:
            if key:
                seen[key] = index
        duplicates = services.find_duplicates(
            legal_name=result.data["legal_name"],
            rccm_number=result.data.get("rccm_number", ""),
            ncc=result.data.get("ncc", ""),
            access=access,
        )
        result.duplicates = [
            {"legal_name": d["legal_name"], "reasons": d["reasons"], "similarity": d.get("similarity")}
            for d in duplicates
        ]
        if any({"rccm", "ncc"} & set(d["reasons"]) for d in duplicates):
            result.status = "ERREUR"
            result.errors["doublon"] = "Une PME avec le même RCCM ou NCC existe déjà : ligne ignorée."
        elif duplicates:
            result.status = "DOUBLON_PROBABLE"
            result.warnings.append(
                "Raison sociale proche d'une PME existante : importée seulement si vous le confirmez."
            )
        results.append(result)
    return columns, results


def run_import(
    access, content: bytes, *, confirm_similar: bool, cohort_id=None, start_onboarding: bool = True
) -> list[RowResult]:
    """Crée les lignes valides (et les doublons probables si confirmés) ; chaque ligne est indépendante."""
    from rest_framework.exceptions import PermissionDenied

    from pme360.audit import services as audit

    from . import services

    if not access.has("pme.create") or access.is_pme_user:
        raise PermissionDenied()
    _, results = analyze(access, content)
    created = 0
    for result in results:
        if result.status == "ERREUR" or (result.status == "DOUBLON_PROBABLE" and not confirm_similar):
            if result.status == "DOUBLON_PROBABLE":
                result.status = "IGNOREE"
            continue
        try:
            with transaction.atomic():
                pme = services.create_pme(
                    access,
                    result.data,
                    primary_person=result.extras.get("primary_person"),
                    advisor_id=result.extras.get("advisor_id"),
                    cohort_id=cohort_id,
                    confirm_duplicates=True,
                    start_onboarding=start_onboarding,
                )
        except (ValidationError, BusinessError, PermissionDenied) as exc:
            result.status = "ERREUR"
            detail = getattr(exc, "detail", str(exc))
            result.errors["creation"] = str(detail if not isinstance(detail, dict) else next(iter(detail.values())))
            continue
        result.status = "CREEE"
        result.pme_id = str(pme.pk)
        created += 1
    audit.record(
        "pme.imported",
        entity_type="organization",
        entity_id=access.organization_id,
        after={
            "rows": len(results),
            "created": created,
            "errors": sum(r.status == "ERREUR" for r in results),
            "ignored": sum(r.status == "IGNOREE" for r in results),
        },
    )
    return results
