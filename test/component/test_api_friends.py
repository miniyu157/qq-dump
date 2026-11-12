"""api: 从明文 profile_info.db 读出好友清单与主人信息。

判定基准: support.profile 中手写的期望记录 OWNER 与 FRIENDS，逐行对应样本库里的一种情形。
"""

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support.profile import FRIENDS, OWNER, write_profile

from api import DatabaseError, Friend, load_friends, load_owner

__all__ = []


class _ProfileCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "profile_info.db"
        write_profile(self.path)

    def _execute(self, statement: str) -> None:
        conn = sqlite3.connect(self.path)
        try:
            conn.execute(statement)
            conn.commit()
        finally:
            conn.close()


class LoadFriendsTests(_ProfileCase):
    def test_friend_records_match_the_expected_ones(self) -> None:
        friends = load_friends(str(self.path))
        self.assertTrue(all(isinstance(friend, Friend) for friend in friends))
        self.assertEqual([friend._asdict() for friend in friends], FRIENDS)

    def test_each_case_of_the_sample(self) -> None:
        # 与上一条重复断言同一批数据，但逐条写出语义，失败时能看出是哪种情形坏了
        by_uid = {friend.uid: friend for friend in load_friends(str(self.path))}
        self.assertNotIn("u_owner", by_uid, "主人的 20001 为 0，不是好友候选")
        self.assertNotIn("u_stranger_f", by_uid, "20001 为 NULL 的资料行不是好友候选")
        self.assertEqual((by_uid["u_friend_a"].is_friend, by_uid["u_friend_a"].deletion_time), (True, None), "在 buddy_list 中的是好友，不报告删除时间")
        self.assertEqual((by_uid["u_deleted_b"].is_friend, by_uid["u_deleted_b"].deletion_time), (False, 1690000000), "不在 buddy_list 中的是已删除好友，20001 为删除时间")
        self.assertEqual((by_uid["u_bot_c"].is_friend, by_uid["u_bot_c"].is_bot), (True, True), "机器人由 profile_info_adelie 判定")
        self.assertEqual(by_uid["u_friend_a"].close_relation, "情侣", "优先取当前展示的密友关系")
        self.assertEqual(by_uid["u_friend_d"].close_relation, "闺蜜", "没有当前关系时取预设列表首项")
        self.assertIsNone(by_uid["u_friend_e"].close_relation, "未登记的关系 ID 不映射名称")
        self.assertEqual((by_uid["u_friend_d"].gender, by_uid["u_friend_d"].gender_name, by_uid["u_friend_d"].group_name), (7, None, None), "未登记的性别与分组保留原始值，名称为空")

    def test_friends_are_listed_in_database_row_order(self) -> None:
        self._execute("""INSERT INTO profile_info_v6 ("1000", "1002", "20001", "20002") VALUES ('u_late_z', 20009, 1600000000, '后来的')""")
        self.assertEqual([friend.uid for friend in load_friends(str(self.path))], [*(friend["uid"] for friend in FRIENDS), "u_late_z"])

    def test_database_is_opened_read_only(self) -> None:
        before = self.path.read_bytes()
        load_friends(str(self.path))
        load_owner(str(self.path))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual([entry.name for entry in self.path.parent.iterdir()], ["profile_info.db"])


class LoadOwnerTests(_ProfileCase):
    def test_owner_record_matches_the_expected_one(self) -> None:
        self.assertEqual(load_owner(str(self.path))._asdict(), OWNER)

    def test_no_owner_uid_recorded(self) -> None:
        self._execute("DELETE FROM category_list_v2")
        self.assertIsNone(load_owner(str(self.path)))

    def test_owner_without_a_profile_row(self) -> None:
        self._execute("""DELETE FROM profile_info_v6 WHERE "1000" = 'u_owner'""")
        self.assertIsNone(load_owner(str(self.path)))


class UnreadableDatabaseTests(unittest.TestCase):
    """库文件打不开或读不了时抛 DatabaseError，消息带上路径，可直接展示给用户。"""

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "profile_info.db"

    def _assert_rejected(self) -> None:
        for load in (load_friends, load_owner):
            with self.subTest(load=load.__name__), self.assertRaises(DatabaseError) as raised:
                load(str(self.path))
            self.assertIn(str(self.path), str(raised.exception))

    def test_missing_file(self) -> None:
        self._assert_rejected()
        self.assertFalse(self.path.exists(), "只读打开不应创建文件")

    def test_file_that_is_not_a_database(self) -> None:
        self.path.write_bytes(b"encrypted or unrelated bytes" * 200)
        self._assert_rejected()

    def test_database_without_the_expected_tables(self) -> None:
        conn = sqlite3.connect(self.path)
        conn.execute("CREATE TABLE unrelated (x)")
        conn.commit()
        conn.close()
        self._assert_rejected()


if __name__ == "__main__":
    unittest.main()
