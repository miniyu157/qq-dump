from . import Column, Status, Table

group_msg_fts = Table(
    "group_msg_fts",
    columns={
        "40021": Column("群号"),
        "40027": Column("群号", status=Status.DISCARDED),  # 极少数消息可能为 0
        "40020": Column("发送人Uid"),
        "40003": Column("msgSeq", status=Status.DISCARDED),
        "40050": Column("msgTime"),
        "40001": Column("msgId"),

        # 客户端注入外挂时两列可能同时有值（样本 2/3621179）
        "41701": Column("消息内容", status=Status.EXPLORING),  # 与 41702 互斥
        "41702": Column("文件名称", status=Status.EXPLORING),  # 与 41701 互斥

        "41703": Column("类型", status=Status.EXPLORING),
        "41704": Column("子类型", status=Status.EXPLORING),
    },
)
