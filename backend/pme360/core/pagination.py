from rest_framework.pagination import CursorPagination


class DefaultCursorPagination(CursorPagination):
    """Pagination par curseur (Document 2, § 6) ; le tri est whitelisté par chaque vue."""

    ordering = "-created_at"
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
