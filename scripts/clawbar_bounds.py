"""収集の上限値。契約上の理由で変えるときは、snapshot契約テストと
製品ドキュメント（ADR-0003の500上限など）をあわせて見直すこと。"""

MAX_METADATA_ITEMS = 500
MAX_COLLECTION_BYTES = 8 * 1024 * 1024
