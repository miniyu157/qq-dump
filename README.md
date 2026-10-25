# QQ DUMP

QQNT 数据库转储、消息导出、好友查询、WebUI，以及专为逆向与开发设计的数据库 Protobuf 研究套件 (Table2D)。

---

**我把 main 分支重写了:**

项目已重写历史记录，包含旧提交的分支在 [dbtools](https://github.com/miniyu157/qq-dump/tree/feat/dbtools) 仍可查看。

项目保留了 legacy 项目 [QQRootFastDecrypt](https://github.com/miniyu157/QQRootFastDecrypt) 的完整消息导出代码，已适配此项目架构。

项目已全面升级到 Python，按需使用依赖:

- blackboxprotobuf (仅 legacy 功能需要)
- pillow (仅终端渲染 avatar 时需要)
- rich (仅 Table2D 研究逆向套件需要)

按需使用二进制依赖:

- sudo (仅自提权时需要)
- sqlcipher (仅解密数据库时需要)
- chafa (仅运行 avatar --chafa 时需要)

---

此文档编辑于: 2026-10-25
即将完善……
即将添加截图和更多用法说明……

---

## 开源许可证

采用 [MIT LICENSE](./LICENSE) 分发
