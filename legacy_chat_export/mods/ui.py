from . import msg as msg
from . import utils as utils
from . import loader as loader

console = msg.Console()


def ui_head(args):
    console.clear()
    head = f"""
[bold]QQNT DUMP CHAT [yellow]ᴀʟᴘʜᴀ[/yellow][/bold]

Github: https://github.com/miniyu157/qq-dump

输入: {args.input}
输出: {args.output}
"""
    console.print(head, justify="center")
    console.print(msg.Rule(style="white"))


def menu_loop(args):
    features = loader.load_features()
    sorted_keys = sorted(
        features.keys(), key=lambda k: features[k]["meta"].get("order", 999)
    )

    with console.screen(hide_cursor=False):
        while True:
            ui_head(args)

            for key in sorted_keys:
                title = features[key]["meta"]["title"]
                msg.print(f"   [{key}] {title}")

            msg.print("   [Q] 退出\n")

            msg.print("等待按下按键: ", end="", flush=True)
            choice = utils.get_key().upper()

            if choice == "Q":
                break

            # 动态分发任务
            if choice in features:
                ui_head(args)

                # 执行对应的 run 函数
                task_func = features[choice]["func"]
                try:
                    task_func(args)
                except Exception as e:
                    msg.error(f"任务执行出错: {e}")

                msg.print()
                utils.wait_any_key()
            else:
                pass
    msg.print("Bye.")
