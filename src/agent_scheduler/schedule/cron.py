"""Cron schedule backend."""

from crontab import CronTab

COMMENT = "agent-scheduler-orchestrator"


def install_cron(executable: str = "agent-scheduler") -> None:
    cron = CronTab(user=True)
    cron.remove_all(comment=COMMENT)
    job = cron.new(
        command=f"{executable} run --no-sync",
        comment=COMMENT,
    )
    job.setall("*/30 * * * *")
    cron.write()


def uninstall_cron() -> None:
    cron = CronTab(user=True)
    cron.remove_all(comment=COMMENT)
    cron.write()


def is_installed() -> bool:
    cron = CronTab(user=True)
    return any(job.comment == COMMENT for job in cron)
