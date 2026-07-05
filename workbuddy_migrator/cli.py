from __future__ import annotations

import argparse
from pathlib import Path

from .backup import create_backup
from .doctor import run_doctor
from .inventory import load_inventory
from .migrate import apply_plan
from .models import AccountInventory, Inventory
from .paths import detect_paths
from .planner import build_plan
from .report import print_json, write_json_report
from .rollback import load_backup_manifest, resolve_manifest_path, rollback_backup
from .verify import verify_plan


def _add_source_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wbm")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--report", type=Path)

    inventory = sub.add_parser("inventory")
    inventory.add_argument("--json", action="store_true")
    inventory.add_argument("--report", type=Path)

    plan = sub.add_parser("plan")
    _add_source_target(plan)
    plan.add_argument("--json", action="store_true")
    plan.add_argument("--report", type=Path)

    backup = sub.add_parser("backup")
    _add_source_target(backup)
    backup.add_argument("--json", action="store_true")

    apply = sub.add_parser("apply")
    _add_source_target(apply)
    apply.add_argument("--yes", action="store_true")
    apply.add_argument("--json", action="store_true")

    migrate = sub.add_parser("migrate")
    migrate.add_argument("--json", action="store_true")

    verify = sub.add_parser("verify")
    _add_source_target(verify)
    verify.add_argument("--json", action="store_true")
    verify.add_argument("--report", type=Path)

    rollback = sub.add_parser("rollback")
    rollback.add_argument("backup_id")
    rollback.add_argument("--json", action="store_true")
    rollback.add_argument("--report", type=Path)

    return parser


def _emit(payload, as_json: bool, report: Path | None = None) -> None:
    if report:
        write_json_report(report, payload)
    if as_json:
        print_json(payload)
    else:
        if isinstance(payload, dict) and payload.get("ok") is False:
            status = "failed"
        elif getattr(payload, "ok", True) is False:
            status = "failed"
        else:
            status = "ok"
        print(f"wbm {status}")


def _compact_user_id(user_id: str) -> str:
    if len(user_id) <= 4:
        return user_id
    return f"{user_id[:4]}...{user_id[-4:]}"


def _display_name(account: AccountInventory) -> str:
    if account.identity and account.identity.display_name:
        return account.identity.display_name
    if account.identity and account.identity.nickname:
        return account.identity.nickname
    if account.identity and account.identity.preferred_username:
        return account.identity.preferred_username
    return "未找到姓名"


def _ordered_accounts(inventory: Inventory) -> list[AccountInventory]:
    return sorted(
        inventory.accounts.values(),
        key=lambda account: (
            not account.is_current,
            -(account.session_count + account.automation_count),
            account.user_id,
        ),
    )


def _print_accounts(accounts: list[AccountInventory]) -> None:
    print(f"发现 {len(accounts)} 个账号：")
    print()
    for index, account in enumerate(accounts, start=1):
        print(f"[{index}] {_compact_user_id(account.user_id)}  {_display_name(account)}")
        status = []
        if account.is_current:
            status.append("当前登录账号")
        status.append(f"{account.session_count} 会话")
        status.append(f"{account.automation_count} 自动化")
        print("    " + " / ".join(status))
        print()


def _choose_account(accounts: list[AccountInventory], prompt: str) -> AccountInventory:
    while True:
        value = input(prompt).strip()
        if value.isdigit():
            index = int(value)
            if 1 <= index <= len(accounts):
                return accounts[index - 1]
        print(f"请输入 1-{len(accounts)} 之间的编号")


def _run_interactive_migrate(inventory: Inventory) -> tuple[AccountInventory, AccountInventory] | None:
    accounts = _ordered_accounts(inventory)
    if len(accounts) < 2:
        print("至少需要两个账号才能迁移")
        return None
    _print_accounts(accounts)
    source = _choose_account(accounts, "从哪个账号迁出？输入编号: ")
    target = _choose_account(accounts, "迁移到哪个账号？输入编号: ")
    if source.user_id == target.user_id:
        print("源账号和目标账号不能相同")
        return None

    print()
    print("确认迁移：")
    print(f"  从 {_compact_user_id(source.user_id)}，{_display_name(source)}，{source.session_count} 会话，{source.automation_count} 自动化")
    print(f"  到 {_compact_user_id(target.user_id)}，{_display_name(target)}，{target.session_count} 会话，{target.automation_count} 自动化")
    confirmed = input("输入 y 开始备份并迁移，其他输入取消: ").strip().lower()
    if confirmed != "y":
        print("已取消")
        return None
    return source, target


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = detect_paths()

    if args.command == "doctor":
        result = run_doctor(paths)
        _emit(result, args.json, args.report)
        return 0 if result["ok"] else 1

    if args.command == "inventory":
        inventory = load_inventory(paths)
        _emit(inventory, args.json, args.report)
        return 0

    if args.command == "plan":
        inventory = load_inventory(paths)
        plan = build_plan(inventory, args.source, args.target)
        _emit(plan, args.json, args.report)
        return 0

    if args.command == "backup":
        inventory = load_inventory(paths)
        plan = build_plan(inventory, args.source, args.target)
        manifest = create_backup(paths, plan)
        _emit(manifest, args.json)
        return 0

    if args.command == "apply":
        if not args.yes:
            raise SystemExit("apply requires --yes in the MVP CLI")
        inventory = load_inventory(paths)
        plan = build_plan(inventory, args.source, args.target)
        manifest = create_backup(paths, plan)
        result = apply_plan(paths, plan, manifest)
        _emit(result, args.json)
        return 0

    if args.command == "migrate":
        inventory = load_inventory(paths)
        selected = _run_interactive_migrate(inventory)
        if selected is None:
            return 1
        source, target = selected
        plan = build_plan(inventory, source.user_id, target.user_id)
        manifest = create_backup(paths, plan)
        result = apply_plan(paths, plan, manifest)
        _emit(result, args.json)
        return 0

    if args.command == "verify":
        inventory = load_inventory(paths)
        plan = build_plan(inventory, args.source, args.target)
        result = verify_plan(paths, plan)
        _emit(result, args.json, args.report)
        return 0 if result["ok"] else 1

    if args.command == "rollback":
        manifest_path = resolve_manifest_path(paths.backups, args.backup_id)
        manifest = load_backup_manifest(manifest_path)
        result = rollback_backup(manifest)
        _emit(result, args.json, args.report)
        return 0 if result["ok"] else 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
