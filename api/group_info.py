"""群资料查询: 群详情、群成员、公告、精华与群通知。

每张表只读取 schema/group_info.py 登记的列。protobuf 列的外层以列号为字段号，
内层字段号见 schema；重复字段展开为列表，未登记的字段不返回。
"""

import sqlite3
from collections.abc import Mapping, Sequence
from typing import NamedTuple

from lib.wire import parse_fields
from schema import Table
from schema.group_info import BULLETIN_DETAIL, BULLETIN_ITEM, group_bulletin, group_detail_info_ver1, group_essence, group_ext_list, group_member3, group_member_level_info, group_notify_list

from .database import connect, resolve_column

__all__ = ["Bulletin", "CustomLabel", "Essence", "GroupAddress", "GroupDetail", "GroupMember", "GroupNotice", "NoticeMember", "load_bulletins", "load_details", "load_essences", "load_members", "load_notices"]

# 公告正文的类型标记，10 是「群公告」这类标题，不属于正文
_BULLETIN_LABEL_TYPE = 10

_DETAIL_FIELDS = ("group_code", "group_name", "remark", "owner_uid", "create_time", "member_count", "max_member_count", "pinned_announce", "description", "labels", "entrance_q", "leave_flag", "custom_labels", "address")
_EXT_FIELDS = ("group_code", "activity_score", "period_msg_count", "lucky_char_content", "owner")
_MEMBER_FIELDS = ("group_code", "uid", "uin", "card", "nickname", "join_time", "last_speak_time", "mute_until", "admin_flag", "member_flag", "custom_title", "member_level")
_ESSENCE_FIELDS = ("group_code", "msg_seq", "msg_random", "sender_uin", "sender_nickname", "set_status", "operator_uin", "operator_nickname", "set_time")
_NOTICE_FIELDS = ("group", "event", "state", "operated_member", "operator_member", "created_time", "operate_time", "remark", "system_remark")


class CustomLabel(NamedTuple):
    """群自定义标签"""

    group_code: int
    label_id: str
    content: str
    setter_uid: str
    set_time: int


class GroupAddress(NamedTuple):
    """群地点；经纬度保留数据库中的整数原值"""

    setter_uid: str
    set_time: int
    location_id: int
    longitude: int
    latitude: int
    location_name: str


class GroupDetail(NamedTuple):
    """一个群的资料；custom_labels 与 address 没有内容时为空列表与 None"""

    group_code: int
    group_name: str
    remark: str
    owner_uid: str
    owner_uin: int | None
    create_time: int
    member_count: int
    max_member_count: int
    pinned_announce: str | None
    description: str | None
    labels: str
    entrance_q: str
    leave_flag: int
    leave_flag_name: str | None
    activity_score: int | None
    period_msg_count: int | None
    lucky_char_content: str
    custom_labels: list[CustomLabel]
    address: GroupAddress | None


class GroupMember(NamedTuple):
    """群成员；level_name 来自该群的等级配置，未配置时为空"""

    group_code: int
    uid: str
    uin: int | None
    card: str
    nickname: str
    join_time: int
    last_speak_time: int
    mute_until: int
    admin_flag: int
    admin_flag_name: str | None
    member_flag: int
    member_flag_name: str | None
    custom_title: str
    member_level: int
    level_name: str | None


class Bulletin(NamedTuple):
    """群公告；text 为正文，已跳过「群公告」这类类型标记项"""

    group_code: int
    publisher_uid: str
    fid: str
    published_time: int
    updated_time: int
    text: str


class Essence(NamedTuple):
    """群精华消息；取消精华的行保留，state 为 2"""

    group_code: int
    msg_seq: int
    msg_random: int
    sender_uin: int
    sender_nickname: str
    state: int
    state_name: str | None
    operator_uin: int
    operator_nickname: str
    set_time: int


class NoticeMember(NamedTuple):
    """群通知中的一方"""

    uid: str
    nickname: str


class GroupNotice(NamedTuple):
    """群通知；created_time 为毫秒，operate_time 为秒"""

    group_code: int | None
    group_name: str
    event: int
    event_name: str | None
    state: int
    state_name: str | None
    operated: NoticeMember | None
    operator: NoticeMember | None
    created_time: int
    operate_time: int
    remark: str
    system_remark: str


def load_details(db_path: str) -> list[GroupDetail]:
    """按 group_code 升序返回全部群资料；群资料库为空时返回空列表"""
    columns = _columns(group_detail_info_ver1, _DETAIL_FIELDS)
    ext_columns = _columns(group_ext_list, _EXT_FIELDS)
    with connect(db_path) as conn:
        ext = {row["group_code"]: row for row in _rows(conn, group_ext_list, ext_columns, order=("group_code",))}
        return [_build_detail(values, ext.get(values["group_code"])) for values in _rows(conn, group_detail_info_ver1, columns, order=("group_code",))]


def load_members(db_path: str, *, include_left: bool = False) -> list[GroupMember]:
    """按 group_code、入群时间升序返回群成员；include_left 为假时只列仍在群的成员"""
    columns = _columns(group_member3, _MEMBER_FIELDS)
    where = "" if include_left else f"WHERE [{columns['member_flag']}] IS NULL OR [{columns['member_flag']}] = 0"
    with connect(db_path) as conn:
        levels = _levels(conn)
        return [_build_member(values, levels) for values in _rows(conn, group_member3, columns, where=where, order=("group_code", "join_time"))]


def load_bulletins(db_path: str) -> list[Bulletin]:
    """按 group_code 返回全部群公告"""
    columns = _columns(group_bulletin, ("group_code", "content"))
    with connect(db_path) as conn:
        return [_build_bulletin(values) for values in _rows(conn, group_bulletin, columns, order=("group_code",))]


def load_essences(db_path: str, *, include_cancelled: bool = False) -> list[Essence]:
    """按 group_code、msg_seq 返回精华消息；include_cancelled 为假时只列当前仍是精华的消息"""
    columns = _columns(group_essence, _ESSENCE_FIELDS)
    where = "" if include_cancelled else f"WHERE [{columns['set_status']}] = 1"
    with connect(db_path) as conn:
        return [_build_essence(values) for values in _rows(conn, group_essence, columns, where=where, order=("group_code", "msg_seq"))]


def load_notices(db_path: str) -> list[GroupNotice]:
    """按时间倒序返回群通知；另行存放的疑似相关通知 (doubt_group_notify_list) 不读取"""
    columns = _columns(group_notify_list, _NOTICE_FIELDS)
    with connect(db_path) as conn:
        return [_build_notice(values) for values in _rows(conn, group_notify_list, columns, order=("created_time",), descending=True)]


def _columns(table: Table, names: Sequence[str]) -> dict[str, str]:
    """语义字段名到列号的映射"""
    return {name: resolve_column(table, name) for name in names}


def _rows(conn: sqlite3.Connection, table: Table, columns: Mapping[str, str], *, where: str = "", order: Sequence[str], descending: bool = False) -> list[dict[str, object]]:
    """按 where 与 order 查询，返回 语义字段名 -> 值；order 为语义名，按列号排序"""
    select = ", ".join(f"[{column}]" for column in columns.values())
    direction = " DESC" if descending else ""
    clause = ", ".join(f"[{columns[name]}]{direction}" for name in order)
    sql = f"SELECT {select} FROM [{table.name}] {where} ORDER BY {clause}"
    return [dict(zip(columns, row)) for row in conn.execute(sql)]


def _payload(blob: object, column: str) -> bytes | None:
    """外层包裹中以列号为字段号的 bytes；列没有内容时返回 None"""
    if not isinstance(blob, bytes) or not blob:
        return None
    return next((value for field, wire, value in parse_fields(blob) or [] if field == int(column) and wire == "bytes"), None)


def _message(payload: bytes | None, proto: Mapping[int, object]) -> dict[str, object]:
    """按登记的字段号展开一层；重复字段为列表，未登记或线型不符的字段跳过"""
    out: dict[str, object] = {}
    for number, wire, value in parse_fields(payload) or []:
        entry = proto.get(number)
        if entry is None:
            continue
        if wire == "bytes":
            value = value.decode("utf-8", errors="replace")
        elif wire in ("fixed32", "fixed64"):
            value = int.from_bytes(value, "little")
        elif wire != "varint":
            continue
        name = entry.name
        if name in out:
            out[name] = [*out[name], value] if isinstance(out[name], list) else [out[name], value]
        else:
            out[name] = value
    return out


def _single(blob: object, table: Table, name: str) -> dict[str, object] | None:
    """单值 protobuf 列展开为一条记录；列没有内容或展开结果为空时返回 None"""
    column = resolve_column(table, name)
    payload = _payload(blob, column)
    if payload is None:
        return None
    return _message(payload, table.columns[column].proto) or None


def _repeated(blob: object, table: Table, name: str) -> list[dict[str, object]]:
    """重复 protobuf 列的每一项展开为一条记录"""
    if not isinstance(blob, bytes) or not blob:
        return []
    column = resolve_column(table, name)
    proto = table.columns[column].proto
    return [_message(value, proto) for field, wire, value in parse_fields(blob) or [] if field == int(column) and wire == "bytes"]


def _levels(conn: sqlite3.Connection) -> dict[int, dict[int, str]]:
    """群号 -> (等级 -> 头衔名)；未配置等级的群不出现在结果中"""
    columns = _columns(group_member_level_info, ("group_code", "levels"))
    levels = {}
    for values in _rows(conn, group_member_level_info, columns, order=("group_code",)):
        levels[values["group_code"]] = {item["level"]: item["level_name"] for item in _repeated(values["levels"], group_member_level_info, "levels")}
    return levels


def _build_detail(values: Mapping[str, object], ext: Mapping[str, object] | None) -> GroupDetail:
    """把群资料行与扩展信息行合并为 GroupDetail"""
    owner = _single(ext["owner"], group_ext_list, "owner") if ext else None
    address = _single(values["address"], group_detail_info_ver1, "address")
    return GroupDetail(
        group_code=values["group_code"],
        group_name=values["group_name"] or "",
        remark=values["remark"] or "",
        owner_uid=values["owner_uid"] or "",
        owner_uin=owner["owner_uin"] if owner else None,
        create_time=values["create_time"] or 0,
        member_count=values["member_count"] or 0,
        max_member_count=values["max_member_count"] or 0,
        pinned_announce=_optional_text(values["pinned_announce"]),
        description=_optional_text(values["description"]),
        labels=values["labels"] or "",
        entrance_q=values["entrance_q"] or "",
        leave_flag=values["leave_flag"] or 0,
        leave_flag_name=group_detail_info_ver1.enum("60340", values["leave_flag"]),
        activity_score=ext["activity_score"] if ext else None,
        period_msg_count=ext["period_msg_count"] if ext else None,
        lucky_char_content=(ext["lucky_char_content"] or "") if ext else "",
        custom_labels=[CustomLabel(_int(item, "group_code"), _text(item, "label_id"), _text(item, "content"), _text(item, "setter_uid"), _int(item, "set_time")) for item in _repeated(values["custom_labels"], group_detail_info_ver1, "custom_labels")],
        address=GroupAddress(_text(address, "setter_uid"), _int(address, "set_time"), _int(address, "location_id"), _int(address, "longitude"), _int(address, "latitude"), _text(address, "location_name")) if address else None,
    )


def _build_member(values: Mapping[str, object], levels: Mapping[int, Mapping[int, str]]) -> GroupMember:
    """把成员行转换为 GroupMember；等级数值对回该群的头衔名"""
    return GroupMember(
        group_code=values["group_code"],
        uid=values["uid"] or "",
        uin=values["uin"],
        card=values["card"] or "",
        nickname=values["nickname"] or "",
        join_time=values["join_time"] or 0,
        last_speak_time=values["last_speak_time"] or 0,
        mute_until=values["mute_until"] or 0,
        admin_flag=values["admin_flag"] or 0,
        admin_flag_name=group_member3.enum("64010", values["admin_flag"]),
        member_flag=values["member_flag"] or 0,
        member_flag_name=group_member3.enum("64016", values["member_flag"]),
        custom_title=values["custom_title"] or "",
        member_level=values["member_level"] or 0,
        level_name=levels.get(values["group_code"], {}).get(values["member_level"]),
    )


def _build_essence(values: Mapping[str, object]) -> Essence:
    """把精华消息行转换为 Essence；取消精华的行保留，状态为 2"""
    return Essence(
        group_code=values["group_code"],
        msg_seq=values["msg_seq"],
        msg_random=values["msg_random"] or 0,
        sender_uin=values["sender_uin"] or 0,
        sender_nickname=values["sender_nickname"] or "",
        state=values["set_status"] or 0,
        state_name=group_essence.enum("67505", values["set_status"]),
        operator_uin=values["operator_uin"] or 0,
        operator_nickname=values["operator_nickname"] or "",
        set_time=values["set_time"] or 0,
    )


def _build_bulletin(values: Mapping[str, object]) -> Bulletin:
    """把公告行转换为 Bulletin，正文取内容项中非类型标记的部分"""
    detail = _payload(_payload(values["content"], resolve_column(group_bulletin, "content")), "64202")
    fields = _message(detail, BULLETIN_DETAIL)
    items = _message_items(_payload(detail, "64227"), BULLETIN_ITEM)
    text = "\n".join(item["text"] for item in items if item.get("type") != _BULLETIN_LABEL_TYPE and item.get("text") is not None)
    return Bulletin(
        group_code=values["group_code"],
        publisher_uid=_text(fields, "publisher_uid"),
        fid=_text(fields, "fid"),
        published_time=_int(fields, "published_time"),
        updated_time=_int(fields, "updated_time"),
        text=text,
    )


def _message_items(payload: bytes | None, proto: Mapping[int, object], number: int = 64242) -> list[dict[str, object]]:
    """把重复出现于同一层的容器展开为若干条记录"""
    return [_message(value, proto) for field, wire, value in parse_fields(payload) or [] if field == number and wire == "bytes"]


def _build_notice(values: Mapping[str, object]) -> GroupNotice:
    """把通知行转换为 GroupNotice；群号与群名取自通知携带的群信息"""
    group = _single(values["group"], group_notify_list, "group")
    operated = _single(values["operated_member"], group_notify_list, "operated_member")
    operator = _single(values["operator_member"], group_notify_list, "operator_member")
    return GroupNotice(
        group_code=group.get("group_code") if group else None,
        group_name=_text(group, "group_name"),
        event=values["event"] or 0,
        event_name=group_notify_list.enum("61002", values["event"]),
        state=values["state"] or 0,
        state_name=group_notify_list.enum("61003", values["state"]),
        operated=NoticeMember(_text(operated, "uid"), _text(operated, "nickname")) if operated else None,
        operator=NoticeMember(_text(operator, "uid"), _text(operator, "nickname")) if operator else None,
        created_time=values["created_time"] or 0,
        operate_time=values["operate_time"] or 0,
        remark=values["remark"] or "",
        system_remark=values["system_remark"] or "",
    )


def _text(fields: Mapping[str, object] | None, name: str) -> str:
    """展开结果中的文本字段，缺失或不是文本时为空串"""
    value = fields.get(name) if fields else None
    return value if isinstance(value, str) else ""


def _int(fields: Mapping[str, object] | None, name: str) -> int:
    """展开结果中的整数字段，缺失或不是整数时为 0"""
    value = fields.get(name) if fields else None
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _optional_text(value: object) -> str | None:
    """文本列原样返回；部分版本把公告与简介存为 BLOB，按 UTF-8 解码"""
    if value is None or isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
