"""Contexte d'accès : permissions (union des rôles) et périmètre sur les PME (Document 1, § 6)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from django.db.models import Q, QuerySet
from django.utils import timezone

from .models import Scope, UserMembership


def active_membership_q() -> Q:
    today = timezone.localdate()
    return Q(is_active=True, valid_from__lte=today) & (Q(valid_to__isnull=True) | Q(valid_to__gte=today))


@dataclass(frozen=True)
class AccessContext:
    user: object
    organization_id: uuid.UUID | None
    memberships: tuple[UserMembership, ...] = ()
    permissions: frozenset[str] = field(default_factory=frozenset)

    def has(self, code: str) -> bool:
        return code in self.permissions

    @property
    def role_codes(self) -> set[str]:
        return {m.role.code for m in self.memberships}

    @property
    def is_pme_user(self) -> bool:
        """Utilisateur côté PME uniquement (portail PME)."""
        return bool(self.memberships) and all(m.role.is_pme_role for m in self.memberships)

    @property
    def own_pme_ids(self) -> set[uuid.UUID]:
        return {m.scope_ref_id for m in self.memberships if m.scope == Scope.PME}

    def pme_scope_q(self) -> Q | None:
        """Filtre de périmètre sur ``Pme`` ; ``None`` = toute l'organisation."""
        condition = Q(pk__in=[])
        for membership in self.memberships:
            if membership.scope == Scope.ORG:
                return None
            if membership.scope == Scope.PROGRAMME:
                condition |= Q(
                    enrollments__cohort__programme_id=membership.scope_ref_id, enrollments__exited_at__isnull=True
                )
            elif membership.scope == Scope.PORTEFEUILLE:
                condition |= Q(assignments__user_id=self.user.pk, assignments__end_date__isnull=True)
            elif membership.scope == Scope.PME:
                condition |= Q(pk=membership.scope_ref_id)
        return condition

    def pme_queryset(self, queryset: QuerySet) -> QuerySet:
        condition = self.pme_scope_q()
        if condition is None:
            return queryset
        # Sous-requête plutôt que .distinct() : compatible avec l'ordonnancement et la pagination par curseur.
        visible_ids = queryset.model.objects.filter(condition).values("pk")
        return queryset.filter(pk__in=visible_ids)


def build_access(user, organization_id: uuid.UUID | None) -> AccessContext:
    if user is None or not user.is_authenticated or organization_id is None:
        return AccessContext(user=user, organization_id=None)
    memberships = tuple(
        UserMembership.objects.filter(active_membership_q(), user=user, organization_id=organization_id)
        .select_related("role")
        .prefetch_related("role__permissions")
    )
    permissions = frozenset(p.code for m in memberships for p in m.role.permissions.all())
    return AccessContext(user=user, organization_id=organization_id, memberships=memberships, permissions=permissions)
