"""cli.keyscan.scan: 从内存字节中收集与排序密钥候选。

判定基准: 手工摆放的假内存。QQ 把算法标记留在密钥附近: 原生构建紧挨着标记，Electron 构建的密钥
离单个标记较远，但落在标记密集处的中心附近。各用例按这两种布局摆放标记与密钥，断言哪些被收集、哪些不被收集。
"""

import unittest

from support.memory import put_anchor

from cli.keyscan.scan import character_class_count, collect_region, key_ok, rank, strong_region

__all__ = []


class KeyWindowTests(unittest.TestCase):
    """密钥是 16 个可打印的非空格字符，且不全是字母数字。"""

    def test_accepts_printable_window_with_a_symbol(self) -> None:
        self.assertTrue(key_ok(b"Abcdef1234567!@#"))

    def test_rejects_other_windows(self) -> None:
        rejected = {"含空格": b"Abcdef 123456!@#", "全是字母数字": b"Abcdef1234567890", "含不可打印字节": b"Abcdef1234567!\x00#", "含 DEL": b"Abcdef1234567!\x7f#", "15 字节": b"Abcdef1234567!@", "17 字节": b"Abcdef1234567!@#$"}
        for reason, window in rejected.items():
            with self.subTest(reason=reason):
                self.assertFalse(key_ok(window))


class RankTests(unittest.TestCase):
    """候选按覆盖的字符类别数 (数字、大写、小写、符号) 降序，其次按出现次数降序，再按字节序。"""

    def test_character_classes(self) -> None:
        self.assertEqual(character_class_count(b"Abcdef1234567!@#"), 4)
        self.assertEqual(character_class_count(b"abcdefghijklmno!"), 2)
        self.assertEqual(character_class_count(b"!!!!!!!!!!!!!!!?"), 1)

    def test_more_classes_first_then_more_frequent_then_bytewise(self) -> None:
        counts = {
            b"!!!!!!!!!!!!!!!?": 99,
            b"ABCDEF1234567!@#": 10,
            b"Abcdef1234567!@#": 1,
            b"abcdef1234567!@#": 20,
            b"abcdef1234567!@$": 20,
            b"abcdefghijklmno!": 50,
        }
        self.assertEqual(rank(counts), [b"Abcdef1234567!@#", b"abcdef1234567!@#", b"abcdef1234567!@$", b"ABCDEF1234567!@#", b"abcdefghijklmno!", b"!!!!!!!!!!!!!!!?"])


class CollectRegionTests(unittest.TestCase):
    def test_native_layout_key_beside_an_anchor(self) -> None:
        memory = bytearray(0x1000)
        put_anchor(memory, 0x800)
        memory[0x900:0x910] = b"nativeKEY!@#$%^&"
        self.assertEqual(collect_region(bytes(memory)), [b"nativeKEY!@#$%^&"])

    def test_nearest_window_to_the_anchor_wins(self) -> None:
        memory = bytearray(0x1000)
        put_anchor(memory, 0x800)
        memory[0x900:0x910] = b"farther!KEY@000#"
        memory[0x7C0:0x7D0] = b"nearer!!KEY@000#"
        self.assertEqual(collect_region(bytes(memory)), [b"nearer!!KEY@000#"])

    def test_electron_layout_key_near_the_dense_cluster(self) -> None:
        memory = bytearray(0x50000)
        for index in range(8):
            put_anchor(memory, 0x2000 + index * 0x200)
        # 距最后一个锚点 0x400，单个锚点的邻近搜索够不到
        memory[0x3200:0x3210] = b"gWDxEK)azQqFNBD<"
        # 远处一个孤立锚点旁的诱饵: 不成簇，也超出邻近范围
        put_anchor(memory, 0x40000)
        memory[0x40400:0x40410] = b"decoyKEY{}|~<>?/"

        found = collect_region(bytes(memory))
        self.assertIn(b"gWDxEK)azQqFNBD<", found)
        self.assertNotIn(b"decoyKEY{}|~<>?/", found)

    def test_cluster_search_gets_past_many_decoys(self) -> None:
        # 证书表之类的数据会在簇中心与密钥之间放下大量形似密钥的窗口
        memory = bytearray(0x50000)
        for index in range(16):
            put_anchor(memory, 0x18000 + index * 0x200)
        center = 0x18F00
        for index in range(1, 152):
            memory[center + index * 0x100:center + index * 0x100 + 16] = f"cert-table-{index:05}".encode()
        memory[center + 152 * 0x100:center + 152 * 0x100 + 16] = b"realKEY)abcDEF!<"
        self.assertIn(b"realKEY)abcDEF!<", collect_region(bytes(memory)))

    def test_key_like_window_without_any_anchor_is_ignored(self) -> None:
        memory = bytearray(0x1000)
        memory[0x100:0x110] = b"loneKEY!@#$%^&*("
        self.assertEqual(collect_region(bytes(memory)), [])

    def test_anchor_off_the_alignment_grid_is_ignored(self) -> None:
        memory = bytearray(0x1000)
        put_anchor(memory, 0x804)
        memory[0x900:0x910] = b"nativeKEY!@#$%^&"
        self.assertEqual(collect_region(bytes(memory)), [])


class StrongRegionTests(unittest.TestCase):
    """strong 模式逐个验证区域内每个对齐窗口，用来找普通模式够不到的密钥。"""

    def test_finds_a_key_far_from_every_anchor(self) -> None:
        memory = bytearray(0x100000)
        put_anchor(memory, 0x1000)
        memory[0x80000:0x80010] = b"strongKEY!@#$%^&"
        self.assertNotIn(b"strongKEY!@#$%^&", collect_region(bytes(memory)))
        self.assertEqual(strong_region(bytes(memory), set(), lambda candidate: candidate == b"strongKEY!@#$%^&"), b"strongKEY!@#$%^&")

    def test_already_tried_candidates_are_not_verified_again(self) -> None:
        memory = bytearray(0x1000)
        memory[0x100:0x110] = b"seenKEY!@#$%^&*("
        memory[0x200:0x210] = b"freshKEY!@#$%^&*"
        tried = []
        seen = {b"seenKEY!@#$%^&*("}
        self.assertIsNone(strong_region(bytes(memory), seen, lambda candidate: tried.append(candidate)))
        self.assertEqual(tried, [b"freshKEY!@#$%^&*"])
        self.assertIn(b"freshKEY!@#$%^&*", seen)

    def test_region_shorter_than_a_key(self) -> None:
        self.assertIsNone(strong_region(b"short", set(), lambda candidate: True))


if __name__ == "__main__":
    unittest.main()
