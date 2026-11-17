"""api.group_info: 从明文 group_info.db 读出群详情、成员、公告、精华与群通知。

判定基准: support.group 中手写的期望记录，逐行对应样本库里的一种情形。
"""

import io
import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support.group import BULLETINS, CANCELLED_ESSENCE, DETAILS, ESSENCES, LEFT_MEMBER, MEMBERS, NOTICES, write_group

from api import DatabaseError, GroupDetail, GroupMember, load_bulletins, load_details, load_essences, load_members, load_notices
from app.output import render_json

__all__ = []


class _GroupCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "group_info.db"
        write_group(self.path)

    def _execute(self, statement: str) -> None:
        conn = sqlite3.connect(self.path)
        try:
            conn.execute(statement)
            conn.commit()
        finally:
            conn.close()

    def _records(self, load, **kwargs) -> list[dict[str, object]]:
        """把查询结果渲染为 JSON 再读回，使嵌套的 NamedTuple 也按字段名比较"""
        sink = io.StringIO()
        render_json((record._asdict() for record in load(str(self.path), **kwargs)), file=sink)
        return json.loads(sink.getvalue())


class LoadDetailsTests(_GroupCase):
    def test_details_match_the_expected_ones(self) -> None:
        self.assertEqual(self._records(load_details), DETAILS)

    def test_detail_records_are_named_tuples(self) -> None:
        self.assertTrue(all(isinstance(record, GroupDetail) for record in load_details(str(self.path))))

    def test_each_case_of_the_sample(self) -> None:
        by_code = {record["group_code"]: record for record in self._records(load_details)}
        self.assertEqual(by_code[10001]["custom_labels"], DETAILS[0]["custom_labels"], "重复字段展开为列表")
        self.assertEqual(by_code[10001]["address"], DETAILS[0]["address"], "嵌套 protobuf 展开为一条记录")
        self.assertEqual(by_code[10001]["owner_uin"], 30001, "群主 QQ 号来自扩展信息表")
        self.assertIsNone(by_code[10002]["owner_uin"], "扩展信息表没有该群时群主 QQ 号为空")
        self.assertIsNone(by_code[10002]["activity_score"], "没有扩展信息行时活跃度为空")
        self.assertEqual(by_code[10003]["leave_flag_name"], "已退群", "退群标志映射为名称")

    def test_groups_without_detail_rows_are_not_listed(self) -> None:
        self.assertEqual([record["group_code"] for record in self._records(load_details)], [record["group_code"] for record in DETAILS])

    def test_empty_database_yields_no_records(self) -> None:
        for table in ("group_detail_info_ver1", "group_ext_list"):
            self._execute(f"DELETE FROM {table}")
        self.assertEqual(load_details(str(self.path)), [])


class LoadMembersTests(_GroupCase):
    def test_members_match_the_expected_ones(self) -> None:
        self.assertEqual(self._records(load_members), MEMBERS)

    def test_level_names_come_from_the_group_configuration(self) -> None:
        by_uid = {record["uid"]: record for record in self._records(load_members)}
        self.assertEqual((by_uid["u_owner_a"]["member_level"], by_uid["u_owner_a"]["level_name"]), (2, "冒泡"))
        self.assertEqual(by_uid["u_member_a2"]["level_name"], "潜水")

    def test_left_members_are_excluded_by_default(self) -> None:
        self.assertNotIn(LEFT_MEMBER["uid"], [record["uid"] for record in self._records(load_members)])
        with_left = self._records(load_members, include_left=True)
        self.assertIn(LEFT_MEMBER, with_left)

    def test_unregistered_level_has_no_name(self) -> None:
        by_uid = {record["uid"]: record for record in self._records(load_members, include_left=True)}
        self.assertEqual((by_uid[LEFT_MEMBER["uid"]]["member_level"], by_uid[LEFT_MEMBER["uid"]]["level_name"]), (9, None))

    def test_members_are_ordered_by_group_then_join_time(self) -> None:
        by_key = [(record["group_code"], record["join_time"]) for record in self._records(load_members)]
        self.assertEqual(by_key, sorted(by_key))

    def test_member_records_are_named_tuples(self) -> None:
        self.assertTrue(all(isinstance(record, GroupMember) for record in load_members(str(self.path))))


class LoadBulletinsTests(_GroupCase):
    def test_bulletins_match_the_expected_ones(self) -> None:
        self.assertEqual(self._records(load_bulletins), BULLETINS)

    def test_title_items_are_skipped_and_paragraphs_joined(self) -> None:
        by_code = {record["group_code"]: record for record in self._records(load_bulletins)}
        self.assertEqual(by_code[10001]["text"], "正文一\n正文二")
        self.assertEqual(by_code[10002]["text"], "", "只有标题项时正文为空，不产生空行")


class LoadEssencesTests(_GroupCase):
    def test_essences_match_the_expected_ones(self) -> None:
        self.assertEqual(self._records(load_essences), ESSENCES)

    def test_cancelled_essences_are_kept_but_excluded_by_default(self) -> None:
        self.assertNotIn(CANCELLED_ESSENCE, self._records(load_essences))
        self.assertIn(CANCELLED_ESSENCE, self._records(load_essences, include_cancelled=True))


class LoadNoticesTests(_GroupCase):
    def test_notices_match_the_expected_ones(self) -> None:
        self.assertEqual(self._records(load_notices), NOTICES)

    def test_notices_are_listed_newest_first(self) -> None:
        times = [record["created_time"] for record in self._records(load_notices)]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_missing_groups_and_operators_are_reported_as_empty(self) -> None:
        by_event = {record["event"]: record for record in self._records(load_notices)}
        self.assertEqual((by_event[6]["group_code"], by_event[6]["group_name"]), (None, ""))
        self.assertIsNone(by_event[1]["operator"], "通知没有操作人时为空")


class UnreadableDatabaseTests(unittest.TestCase):
    """库文件打不开或读不了时抛 DatabaseError，消息带上路径，可直接展示给用户。"""

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "group_info.db"

    def _assert_rejected(self) -> None:
        for load in (load_details, load_members, load_bulletins, load_essences, load_notices):
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
