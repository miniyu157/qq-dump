DB_MSG = "nt_msg.db"  # 消息数据库

# C2C单聊消息表
Table_C2c_msg = "c2c_msg_table"

Col_sender_uid = "40020"  # 发送者UID(少数时候会与 40021 相等, 则为自己发出的消息; 如果为空则是系统消息)
Col_peer_uid = "40021"  # 接受者UID
Col_timespan = "40050"  # 秒级消息时间戳
Col_msg = "40800"  # 消息内容, 多层套娃的 Protobuf


# 群聊消息表, 暂不处理
Table_group_msg = "group_msg_table"


DB_PROFILE = "profile_info.db"  # 用户信息数据库
# 存储分组信息和主人UID的表, 一般只有一行
# 列 1000(主人UID), 25011(protobuf 分组信息)
# 二进制 25011 内部结构: 25007(分组ID,0为'我的好友'), 25008(分组名称)
Table_category_list = "category_list_v2"
# 用户信息贮藏表
# 列 1000(UID), 1001(QID,NULL?), 1002(QQ),
# 20002(昵称), 20009(主人设置的备注,NULL?), 20011(个性签名,NULL?)
Table_profile_info = "profile_info_v6"
# 好友列表
# 列 1000(UID), 25007(分组ID)
Table_buddy_list = "buddy_list_v2"
