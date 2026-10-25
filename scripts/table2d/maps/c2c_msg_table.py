from . import Column, ProtoField, Status, Table

c2c_msg_table = Table(
    "c2c_msg_table",
    columns={
        "40001": Column("msgId"),  # 全局唯一 ID
        "40002": Column("msgRandom", status=Status.DISCARDED),  # 消息随机数
        "40003": Column("msgSeq", status=Status.DISCARDED),  # 全局倒序序号
        "40005": Column("clientSeq", status=Status.DISCARDED),  # 全局倒序序号
        "40011": Column("msgType", status=Status.DISCARDED),  # 外层消息类型
        "40012": Column("subMsgType", status=Status.DISCARDED),  # 外层消息子类型
        "40020": Column("senderUid"),  # 消息发送方，可能为主人 UID 或会话目标 UID
        "40021": Column("peerUid"),  # 会话目标 UID，勿与消息接收方混淆
        "40030": Column("peerUin", status=Status.DISCARDED),  # 可能为主人 UIN 或会话目标 UIN
        "40033": Column("senderUin", status=Status.DISCARDED),  # 发送方 UIN，可能为主人 UIN 或会话目标 UIN
        # 发送方昵称：主人发出的消息几乎都写；对方发来的普通消息不写，
        # 但通话这类需要对方名字的记录会写；系统消息从不写。
        "40093": Column("senderNick"),
        "40058": Column("当日零点时间戳", status=Status.DISCARDED),
        "40800": Column(
            "消息体",
            proto={
                45001: ProtoField("elementId", status=Status.DISCARDED),  # 段级 ID
                45002: ProtoField("elementType"),  # 消息类型
                45003: ProtoField("subMsgType"),  # 消息子类型
                45101: ProtoField("content"),  # 文本正文，UTF-8 编码
                # 不可检索的复杂嵌套：图片主机名、rkey、按 spec 展开的下载路径；
                # 信息重复较多
                45600: ProtoField("媒体下载描述", status=Status.DISCARDED),
                48214: ProtoField("系统灰条 XML"),
            },
        ),
        "40050": Column("msgTime"),  # 消息时间戳
    },
)
