"""数据库访问 API：好友清单与主人信息查询。"""

from .friends import Friend, load_friends, load_owner

__all__ = ["Friend", "load_friends", "load_owner"]
