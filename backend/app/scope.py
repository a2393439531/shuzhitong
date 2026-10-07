"""行级数据范围（部门级）：super_admin 看全量，其余角色只看本部门数据。

约定：凡是需要做行级过滤的 SQL 模板，一律写成
    ... WHERE 1=1 {dept_filter} ...
的形式，执行前调用 apply_scope(sql, user) 做替换。
占位符会被替换为 ""（super_admin）或 "AND dept = ?"（带参数），
要求模板查询的表中有名为 dept 的列。

原创实现。
"""

DEPT_PLACEHOLDER = "{dept_filter}"


def is_super_admin(user) -> bool:
    return user["role"] == "super_admin"


def dept_filter_clause(user) -> tuple:
    """返回 (子句片段, 参数列表)。"""
    if is_super_admin(user):
        return "", []
    return "AND dept = ?", [user["dept"]]


def apply_scope(sql: str, user) -> tuple:
    """把 SQL 模板中的 {dept_filter} 替换为实际子句。返回 (sql, params)。"""
    clause, params = dept_filter_clause(user)
    return sql.replace(DEPT_PLACEHOLDER, clause), params
